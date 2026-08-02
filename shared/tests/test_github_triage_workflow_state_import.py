"""End-to-end: a deleted workflow never reaches the triage store.

Covers iterate-2026-08-01-ci-card-deleted-workflow AC1 (through
`import_findings`), AC7 (an already-open card auto-resolves), AC8 (a FAILED
state lookup resolves nothing) and AC10 (a failed runs fetch resolves nothing).
The reducer/client unit coverage lives in the sibling
`test_github_triage_workflow_state.py`.

Fixtures are duplicated from that module rather than imported: sibling
test-module imports are exactly the cross-root coupling ADR-044 warns about,
and two dicts are cheaper than the coupling.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import github_api  # noqa: E402
import github_triage  # noqa: E402
import github_workflow_api  # noqa: E402
from triage import append_triage_item, read_all_items  # noqa: E402

DELETED_WORKFLOW_ID = 322548704
LIVE_WORKFLOW_ID = 259825683

DELETED_RUN = {
    "id": 30404435116,
    "workflow_id": DELETED_WORKFLOW_ID,
    "name": "Probe refresh-token bypass",
    "head_branch": "main",
    "head_sha": "2a5b7d35e4c0134c7f46db23129584a3cf8a3f95",
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/svenroth-ai/shipwright/actions/runs/30404435116",
}

LIVE_RUN = {
    "id": 30692857884,
    "workflow_id": LIVE_WORKFLOW_ID,
    "name": "CodeQL",
    "head_branch": "main",
    "head_sha": "62c92866770e7dc33e27f9c5ebd5948665f6f780",
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/svenroth-ai/shipwright/actions/runs/30692857884",
}

_CI_TITLE = "[ci] Probe refresh-token bypass failing on main"


def _deleted_only(workflow_id):
    return "deleted" if workflow_id == DELETED_WORKFLOW_ID else "active"


#: Sentinel for `_patch_import(state_fetcher=...)` meaning "do NOT override the
#: state fetcher — leave conftest's autouse default in place". Distinct from
#: `None`, which is itself a meaningful fetcher return (state unknown).
_KEEP_CONFTEST_DEFAULT = object()


def _patch_import(monkeypatch, *, runs, state_fetcher, owner_repo="acme/foo"):
    """Silence every feed except CI so the assertions are about gh-ci only."""
    monkeypatch.setattr(github_api, "gh_available", lambda: True)
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    monkeypatch.setattr(github_api, "fetch_code_scanning_alerts", lambda: None)
    monkeypatch.setattr(github_api, "fetch_dependabot_alerts", lambda: None)
    monkeypatch.setattr(github_api, "fetch_secret_scanning_alerts", lambda: None)
    monkeypatch.setattr(github_api, "fetch_workflow_runs", lambda branch: runs)
    if state_fetcher is not _KEEP_CONFTEST_DEFAULT:
        monkeypatch.setattr(
            github_workflow_api, "fetch_workflow_state", state_fetcher
        )
    monkeypatch.setattr(github_api, "owner_repo", lambda _: owner_repo)
    monkeypatch.setattr(github_api, "latest_security_workflow_run", lambda: None)
    monkeypatch.setattr(
        github_api, "download_security_findings",
        lambda rid, workflow_base=None: None,
    )
    monkeypatch.setattr(github_api, "download_prompt_risks", lambda rid: None)
    # PR-CI is a separate producer with its own resolve path — keep it dormant.
    monkeypatch.setattr(
        github_triage.consumer, "import_pr_ci_findings",
        lambda root, owner, append_fn=None: {
            "appended": 0, "emitted": 0, "resolved": 0,
        },
    )


def _ci_keys(project_root: Path) -> set[str]:
    """Every `gh-ci:` dedup key that was APPENDED to the store."""
    path = project_root / ".shipwright" / "triage.jsonl"
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = obj.get("dedupKey") or ""
        if obj.get("event") == "append" and key.startswith("gh-ci:"):
            keys.add(key)
    return keys


def _status_of(project_root: Path, dedup_key: str):
    for item in read_all_items(project_root):
        if item.get("dedupKey") == dedup_key:
            return item.get("status")
    return None


def _reason_of(project_root: Path, dedup_key: str):
    for item in read_all_items(project_root):
        if item.get("dedupKey") == dedup_key:
            return item.get("statusReason")
    return None


def _seed_open_card(project_root: Path, workflow_id: int, title: str) -> None:
    append_triage_item(
        project_root, source="github", severity="high", kind="bug",
        title=title, detail="seeded", dedup_key=f"gh-ci:{workflow_id}",
        launch_payload="/shipwright-iterate --type bug",
    )


def test_import_files_no_card_for_deleted_workflow(tmp_path, monkeypatch):
    """AC1 end-to-end — the deleted workflow never reaches the triage store,
    and the LIVE workflow's failure still does, in the same import."""
    _patch_import(
        monkeypatch, runs=[DELETED_RUN, LIVE_RUN], state_fetcher=_deleted_only
    )
    github_triage.import_findings(tmp_path)

    keys = _ci_keys(tmp_path)
    assert f"gh-ci:{DELETED_WORKFLOW_ID}" not in keys, (
        "an unfixable card for a deleted workflow reached the inbox"
    )
    assert f"gh-ci:{LIVE_WORKFLOW_ID}" in keys, (
        "a real CI failure was suppressed — the dangerous direction"
    )


def test_import_resolves_open_card_for_deleted_workflow(tmp_path, monkeypatch):
    """AC7 — the fix closes cards already sitting in the inbox, not just future
    ones: the key leaves `current_keys`, so `resolve_stale` dismisses it."""
    _seed_open_card(tmp_path, DELETED_WORKFLOW_ID, _CI_TITLE)
    assert _status_of(tmp_path, f"gh-ci:{DELETED_WORKFLOW_ID}") == "triage"

    _patch_import(
        monkeypatch, runs=[DELETED_RUN, LIVE_RUN], state_fetcher=_deleted_only
    )
    github_triage.import_findings(tmp_path)

    assert _status_of(tmp_path, f"gh-ci:{DELETED_WORKFLOW_ID}") == "dismissed"
    # The reason is half the AC: `githubResolved` says the producer's own sweep
    # closed it because the key left the finding set — a `schemaMigration`
    # dismissal would be the same status for an entirely different cause.
    assert _reason_of(tmp_path, f"gh-ci:{DELETED_WORKFLOW_ID}") == "githubResolved"


def test_failed_state_lookup_does_not_resolve_card(tmp_path, monkeypatch):
    """AC8 — a state fetch that FAILED must not read as 'the finding cleared'.

    Fail-open keeps the run, so its key stays in `current_keys` and the open
    card survives to be retried next cycle. Mirrors FR-01.14: an import that
    failed closes nothing.
    """
    _seed_open_card(tmp_path, DELETED_WORKFLOW_ID, _CI_TITLE)

    _patch_import(
        monkeypatch,
        runs=[DELETED_RUN, LIVE_RUN],
        state_fetcher=lambda wid: None,  # every lookup fails
    )
    github_triage.import_findings(tmp_path)

    assert _status_of(tmp_path, f"gh-ci:{DELETED_WORKFLOW_ID}") == "triage"


def test_default_fixture_prevents_a_live_workflow_state_lookup(tmp_path, monkeypatch):
    """Ledger row 24 — with ONLY conftest's autouse default in place (no local
    override), a failing run must not reach the live `gh` transport.

    Asserted on the transport itself, because "the suite is green" cannot tell
    "no live call was made" apart from "a live call was made and happened to
    404" — which is precisely how this escaped the first review. `_gh_api` is
    the single chokepoint every client goes through, so a recorder there sees
    any leak regardless of which client opens it.
    """
    requested: list[str] = []

    def recording_gh_api(path, **kwargs):
        requested.append(path)
        return None

    monkeypatch.setattr(github_api, "_gh_api", recording_gh_api)
    _patch_import(
        monkeypatch,
        runs=[DELETED_RUN, LIVE_RUN],
        state_fetcher=_KEEP_CONFTEST_DEFAULT,
    )
    github_triage.import_findings(tmp_path)

    assert not [p for p in requested if "actions/workflows/" in p], (
        f"a live workflow-state lookup escaped the default isolation: {requested}"
    )
    # And the fail-open default means both failed runs still card, exactly as
    # they did before this client existed.
    assert _ci_keys(tmp_path) == {
        f"gh-ci:{DELETED_WORKFLOW_ID}", f"gh-ci:{LIVE_WORKFLOW_ID}",
    }


def test_failed_runs_fetch_resolves_no_ci_cards(tmp_path, monkeypatch):
    """AC10 — the pre-existing gate this change must not erode: when the
    workflow-RUNS fetch fails, PREFIX_CI is not resolvable and no gh-ci card is
    closed. Without it an upstream outage would empty `current_keys` and
    mass-resolve every real CI finding."""
    _seed_open_card(tmp_path, LIVE_WORKFLOW_ID, "[ci] CodeQL failing on main")

    _patch_import(
        monkeypatch,
        runs=None,  # the runs fetch itself failed
        state_fetcher=lambda wid: "active",
    )
    github_triage.import_findings(tmp_path)

    assert _status_of(tmp_path, f"gh-ci:{LIVE_WORKFLOW_ID}") == "triage"

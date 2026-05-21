"""Action-unit emission + legacy migration tests.

Iterate-2026-05-20-triage-launch-surface AC-1, AC-2, AC-7 (action-units +
launchPayload + per-source-gated legacy migration). Supersedes the
per-finding mapping tests in test_github_triage.py.

The four production code paths under test:

- ``security_action_unit(cs_alerts, db_alerts, owner_repo)`` — collapses
  code-scanning + dependabot into ONE unit per repo.
- ``secrets_action_unit(ss_alerts, owner_repo)`` — collapses
  secret-scanning into ONE unit per repo, whitelist-only payload (no
  alert content).
- ``ci_action_unit(run, owner_repo)`` — one unit per failed default-branch
  workflow, dedup key drops the head_sha.
- ``import_findings`` — orchestrator emits action-units and migrates
  legacy per-finding items per-source-gated.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import github_api  # noqa: E402
import github_triage  # noqa: E402
from triage import append_triage_item, read_all_items  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture alerts (trimmed to fields the mappers actually read)
# ---------------------------------------------------------------------------

CS_HIGH = {
    "number": 42, "state": "open",
    "rule": {
        "id": "py/sql-injection", "severity": "error",
        "security_severity_level": "high",
        "description": "SQL query built from user-controlled sources",
    },
    "most_recent_instance": {"location": {"path": "app/db.py", "start_line": 88}},
    "html_url": "https://github.com/acme/foo/security/code-scanning/42",
}
CS_MEDIUM = {
    "number": 43, "state": "open",
    "rule": {"id": "py/xss", "severity": "warning",
             "security_severity_level": "medium",
             "description": "Reflected XSS"},
    "most_recent_instance": {"location": {"path": "app/view.py", "start_line": 12}},
    "html_url": "https://github.com/acme/foo/security/code-scanning/43",
}
DB_CRITICAL = {
    "number": 7, "state": "open",
    "security_advisory": {"severity": "critical", "summary": "Prototype pollution"},
    "dependency": {"package": {"name": "lodash"}},
    "html_url": "https://github.com/acme/foo/security/dependabot/7",
}
DB_LOW = {
    "number": 8, "state": "open",
    "security_advisory": {"severity": "low", "summary": "Out-of-bounds in glob"},
    "dependency": {"package": {"name": "glob"}},
    "html_url": "https://github.com/acme/foo/security/dependabot/8",
}

_SENTINEL = "SENTINEL-do-not-leak-fixture-marker"
SS_ONE = {
    "number": 3, "state": "open",
    "secret_type": "github_personal_access_token",
    "secret_type_display_name": "GitHub Personal Access Token",
    "secret": _SENTINEL,
    "html_url": "https://github.com/acme/foo/security/secret-scanning/3",
}
SS_TWO = {
    "number": 4, "state": "open",
    "secret_type": "aws_access_key_id",
    "secret_type_display_name": "Amazon AWS Access Key ID",
    "secret": _SENTINEL,
    "html_url": "https://github.com/acme/foo/security/secret-scanning/4",
}

CI_FAILED = {
    "id": 900, "workflow_id": 1, "name": "CI", "head_branch": "main",
    "head_sha": "abc1234def567", "status": "completed", "conclusion": "failure",
    "html_url": "https://github.com/acme/foo/actions/runs/900",
}

OWNER_REPO = "acme/foo"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _append_events(project_root: Path) -> list[dict]:
    path = project_root / ".shipwright" / "triage.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("event") == "append":
            out.append(obj)
    return out


def _patch_api(
    monkeypatch,
    *,
    code_scanning=None,
    dependabot=None,
    secret_scanning=None,
    runs=None,
    available=True,
    branch="main",
    owner_repo_value: str | None = OWNER_REPO,
):
    monkeypatch.setattr(github_api, "gh_available", lambda: available)
    monkeypatch.setattr(github_api, "default_branch", lambda: branch)
    monkeypatch.setattr(
        github_api, "fetch_code_scanning_alerts", lambda: code_scanning
    )
    monkeypatch.setattr(github_api, "fetch_dependabot_alerts", lambda: dependabot)
    monkeypatch.setattr(
        github_api, "fetch_secret_scanning_alerts", lambda: secret_scanning
    )
    monkeypatch.setattr(github_api, "fetch_workflow_runs", lambda branch: runs)
    monkeypatch.setattr(github_api, "owner_repo", lambda _: owner_repo_value)
    # Stub the artifact-path fetchers (Iterate C). Without these, tests
    # run inside a worktree whose origin has a real ``security.yml``
    # workflow leak production data into the artifact fallback and emit
    # an unintended ``gh-security:`` action-unit — defeating any
    # partial-fetch assertions below. Action-unit tests targeting the
    # API path explicitly opt out of the artifact path; per-artifact
    # tests live in test_github_triage_artifact_fallback.py and patch
    # these directly.
    monkeypatch.setattr(
        github_api, "latest_security_workflow_run", lambda: None,
    )
    monkeypatch.setattr(
        github_api, "download_security_findings", lambda run_id: None,
    )


# ---------------------------------------------------------------------------
# AC-1, AC-2 — security_action_unit
# ---------------------------------------------------------------------------

def test_security_action_unit_collapses_both_feeds() -> None:
    """ONE dict per repo with combined count + max severity."""
    item = github_triage.security_action_unit(
        code_scanning=[CS_HIGH, CS_MEDIUM],
        dependabot=[DB_CRITICAL, DB_LOW],
        owner_repo=OWNER_REPO,
    )
    assert item is not None
    assert item["dedup_key"] == "gh-security:acme/foo"
    # max severity across BOTH feeds — critical wins
    assert item["severity"] == "critical"
    assert item["kind"] == "bug"
    # Title carries the human-readable counts
    assert "2 code-scanning" in item["title"]
    assert "2 Dependabot" in item["title"]
    # Detail mentions the breakdown
    assert "critical" in item["detail"].lower()


def test_security_action_unit_launch_payload_shape() -> None:
    item = github_triage.security_action_unit(
        code_scanning=[CS_HIGH], dependabot=[], owner_repo=OWNER_REPO,
    )
    payload = item["launch_payload"]
    # Starts with the slash command (AC-2)
    assert payload.startswith("/shipwright-security")
    # Contains the GitHub security tab URL (stable across runs)
    assert "https://github.com/acme/foo/security" in payload
    # Does NOT contain the per-finding URL (frozen-payload must use stable tab URL)
    assert "code-scanning/42" not in payload


def test_security_action_unit_payload_deterministic() -> None:
    """Review finding #6: re-shuffled alert order yields byte-identical payload."""
    a = github_triage.security_action_unit(
        code_scanning=[CS_HIGH, CS_MEDIUM], dependabot=[DB_CRITICAL, DB_LOW],
        owner_repo=OWNER_REPO,
    )
    b = github_triage.security_action_unit(
        code_scanning=[CS_MEDIUM, CS_HIGH],  # reordered
        dependabot=[DB_LOW, DB_CRITICAL],  # reordered
        owner_repo=OWNER_REPO,
    )
    assert a["launch_payload"] == b["launch_payload"]
    assert a["title"] == b["title"]


def test_security_action_unit_returns_none_when_empty() -> None:
    """No alerts at all → no item to emit."""
    item = github_triage.security_action_unit(
        code_scanning=[], dependabot=[], owner_repo=OWNER_REPO,
    )
    assert item is None


def test_security_action_unit_returns_none_when_owner_repo_none() -> None:
    """owner_repo unresolved → producer skips (no malformed key like
    ``gh-security:``)."""
    item = github_triage.security_action_unit(
        code_scanning=[CS_HIGH], dependabot=[], owner_repo=None,
    )
    assert item is None


# ---------------------------------------------------------------------------
# AC-2 (secret-scanning) — whitelist-only payload (review finding #9)
# ---------------------------------------------------------------------------

def test_secrets_action_unit_payload_is_whitelist_only() -> None:
    item = github_triage.secrets_action_unit(
        secret_scanning=[SS_ONE, SS_TWO], owner_repo=OWNER_REPO,
    )
    assert item is not None
    assert item["dedup_key"] == "gh-secrets:acme/foo"
    assert item["severity"] == "critical"

    payload = item["launch_payload"]
    # No slash command — rotation is manual by design
    assert "/shipwright-" not in payload
    # Carries the secret-scanning tab URL (stable, repo-level)
    assert "https://github.com/acme/foo/security/secret-scanning" in payload
    # Per-alert URLs MUST NOT appear in the payload
    assert "/secret-scanning/3" not in payload
    assert "/secret-scanning/4" not in payload
    # Per-alert content MUST NOT appear (no display names, no secret_type, no html_url)
    assert "GitHub Personal Access Token" not in payload
    assert "Amazon AWS Access Key ID" not in payload
    assert "github_personal_access_token" not in payload
    assert "aws_access_key_id" not in payload
    # Sentinel: the raw secret value must NEVER appear
    assert _SENTINEL not in payload


def test_secrets_action_unit_detail_does_not_leak_alert_content() -> None:
    """Detail field also follows the hygiene boundary (it's persisted too)."""
    item = github_triage.secrets_action_unit(
        secret_scanning=[SS_ONE, SS_TWO], owner_repo=OWNER_REPO,
    )
    assert _SENTINEL not in item["detail"]
    assert "GitHub Personal Access Token" not in item["detail"]
    assert "Amazon AWS Access Key ID" not in item["detail"]


def test_secrets_action_unit_returns_none_when_empty() -> None:
    assert github_triage.secrets_action_unit(
        secret_scanning=[], owner_repo=OWNER_REPO,
    ) is None


def test_secrets_action_unit_returns_none_when_owner_repo_none() -> None:
    assert github_triage.secrets_action_unit(
        secret_scanning=[SS_ONE], owner_repo=None,
    ) is None


# ---------------------------------------------------------------------------
# AC-2 (ci) — workflow page URL, dedup key drops sha (review finding #7)
# ---------------------------------------------------------------------------

def test_ci_action_unit_drops_sha_from_dedup_key() -> None:
    item = github_triage.ci_action_unit(CI_FAILED, owner_repo=OWNER_REPO)
    assert item is not None
    # NO sha component (different from #39 which was ``gh-ci:1:abc1234def567``)
    assert item["dedup_key"] == "gh-ci:1"
    assert ":abc1234def567" not in item["dedup_key"]
    assert item["severity"] == "high"
    assert item["kind"] == "bug"


def test_ci_action_unit_payload_uses_workflow_page_url() -> None:
    """Workflow PAGE URL (stable across runs), not the per-run URL — review #7.

    The dedup key drops the sha so the on-disk launchPayload is frozen at
    first emit. Linking to a specific run would be stale on the next CI
    failure for the same workflow.
    """
    item = github_triage.ci_action_unit(CI_FAILED, owner_repo=OWNER_REPO)
    payload = item["launch_payload"]
    assert payload.startswith("/shipwright-iterate --type bug")
    # Workflow page URL, e.g. .../actions/workflows/{workflow_id}
    assert "/actions/workflows/1" in payload
    # NOT the per-run URL
    assert "/actions/runs/900" not in payload


def test_ci_action_unit_returns_none_when_owner_repo_none() -> None:
    """Repo-scoped URL requires owner_repo. Skip emission rather than malform."""
    assert github_triage.ci_action_unit(CI_FAILED, owner_repo=None) is None


# ---------------------------------------------------------------------------
# AC-1 — import_findings emits ONE action-unit per category (not per finding)
# ---------------------------------------------------------------------------

def test_import_findings_emits_action_units_not_per_finding(
    project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_api(
        monkeypatch,
        code_scanning=[CS_HIGH, CS_MEDIUM],
        dependabot=[DB_CRITICAL, DB_LOW],
        secret_scanning=[SS_ONE, SS_TWO],
        runs=[CI_FAILED],
    )
    result = github_triage.import_findings(project)
    assert result["gh_available"] is True
    # 1 security + 1 secrets + 1 ci = 3 action-units (NOT 4 cs + 4 db + 2 ss + 1 ci = 11)
    assert result["appended"] == 3
    keys = sorted(e["dedupKey"] for e in _append_events(project))
    assert keys == sorted([
        "gh-security:acme/foo",
        "gh-secrets:acme/foo",
        "gh-ci:1",
    ])
    # Every emitted action-unit carries a non-empty launchPayload (AC-2)
    for event in _append_events(project):
        assert event["launchPayload"], (
            f"action-unit {event['dedupKey']} must carry launchPayload"
        )


def test_import_findings_idempotent_payload_frozen(
    project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-8: second import does not append a duplicate; original payload stays."""
    _patch_api(
        monkeypatch, code_scanning=[CS_HIGH], dependabot=[], secret_scanning=[],
        runs=[],
    )
    first = github_triage.import_findings(project)
    [first_event] = _append_events(project)
    original_payload = first_event["launchPayload"]

    # Second run with DIFFERENT alert set (more findings) — payload would change
    # if it weren't frozen. Same dedup key → duplicate suppressed.
    _patch_api(
        monkeypatch, code_scanning=[CS_HIGH, CS_MEDIUM], dependabot=[DB_CRITICAL],
        secret_scanning=[], runs=[],
    )
    second = github_triage.import_findings(project)
    assert first["appended"] == 1
    assert second["appended"] == 0
    [only_event] = _append_events(project)
    assert only_event["launchPayload"] == original_payload, (
        "AC-8: payload frozen at first append"
    )


def test_import_findings_skips_repo_scoped_when_owner_repo_none(
    project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-10: unresolvable owner/repo → no gh-security / gh-secrets emitted.
    CI still emits (its mapper also needs owner_repo for the URL — both skip).
    """
    _patch_api(
        monkeypatch, code_scanning=[CS_HIGH], dependabot=[],
        secret_scanning=[SS_ONE], runs=[CI_FAILED],
        owner_repo_value=None,
    )
    result = github_triage.import_findings(project)
    keys = {e["dedupKey"] for e in _append_events(project)}
    # No gh-security / gh-secrets / gh-ci items — all need owner_repo.
    assert keys == set()
    assert result["appended"] == 0


# ---------------------------------------------------------------------------
# AC-7 — legacy migration (per-source-gated, review finding #3)
# ---------------------------------------------------------------------------

def _seed_legacy_item(project: Path, dedup_key: str) -> str:
    """Append a legacy per-finding item directly (simulates a pre-iterate run)."""
    return append_triage_item(
        project, source="github", severity="high", kind="bug",
        title="legacy", detail="d", dedup_key=dedup_key,
    )


def test_legacy_items_migrated_when_all_fetches_succeed(
    project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All 4 fetches succeed (empty) → all 4 legacy items migrated."""
    cs_id = _seed_legacy_item(project, "github:code-scanning:42")
    db_id = _seed_legacy_item(project, "github:dependabot:7")
    ss_id = _seed_legacy_item(project, "github:secret-scanning:3")
    ci_id = _seed_legacy_item(project, "github-ci:1:abc1234def567")

    _patch_api(
        monkeypatch, code_scanning=[], dependabot=[], secret_scanning=[], runs=[],
    )
    github_triage.import_findings(project)

    resolved = {it["id"]: it for it in read_all_items(project)}
    for legacy_id in (cs_id, db_id, ss_id, ci_id):
        assert resolved[legacy_id]["status"] == "dismissed"
        assert resolved[legacy_id]["statusReason"] == "schemaMigration"


def test_legacy_migration_is_idempotent(
    project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review finding #12: second run does NOT re-dismiss the same legacy item."""
    cs_id = _seed_legacy_item(project, "github:code-scanning:42")
    _patch_api(
        monkeypatch, code_scanning=[], dependabot=[], secret_scanning=[], runs=[],
    )
    github_triage.import_findings(project)
    # Capture the status-event count.
    path = project / ".shipwright" / "triage.jsonl"
    status_events_before = sum(
        1 for line in path.read_text(encoding="utf-8").splitlines()
        if line and json.loads(line).get("event") == "status"
    )
    github_triage.import_findings(project)
    status_events_after = sum(
        1 for line in path.read_text(encoding="utf-8").splitlines()
        if line and json.loads(line).get("event") == "status"
    )
    assert status_events_after == status_events_before, (
        "second migration sweep must NOT append redundant schemaMigration events"
    )
    # And the item is still dismissed.
    [item] = [i for i in read_all_items(project) if i["id"] == cs_id]
    assert item["status"] == "dismissed"


@pytest.mark.parametrize(
    "failed_source,legacy_prefix,other_prefixes",
    [
        # When CS fetch fails: legacy CS items survive; others migrate.
        (
            "code_scanning",
            "github:code-scanning:42",
            [
                "github:dependabot:7",
                "github:secret-scanning:3",
                "github-ci:1:abc1234def567",
            ],
        ),
        (
            "dependabot",
            "github:dependabot:7",
            [
                "github:code-scanning:42",
                "github:secret-scanning:3",
                "github-ci:1:abc1234def567",
            ],
        ),
        (
            "secret_scanning",
            "github:secret-scanning:3",
            [
                "github:code-scanning:42",
                "github:dependabot:7",
                "github-ci:1:abc1234def567",
            ],
        ),
        (
            "runs",
            "github-ci:1:abc1234def567",
            [
                "github:code-scanning:42",
                "github:dependabot:7",
                "github:secret-scanning:3",
            ],
        ),
    ],
)
def test_legacy_migration_per_source_gated(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_source: str,
    legacy_prefix: str,
    other_prefixes: list[str],
) -> None:
    """Review finding #3: a failed fetch for ONE source must not migrate that
    source's legacy items, while the other three sources still get migrated.
    Preserves the ADR-052 fail-soft invariant.
    """
    legacy_id = _seed_legacy_item(project, legacy_prefix)
    other_ids = [_seed_legacy_item(project, p) for p in other_prefixes]

    # Patch with `None` for the failed source, `[]` for the others.
    kwargs = {
        "code_scanning": [], "dependabot": [], "secret_scanning": [], "runs": [],
    }
    kwargs[failed_source] = None
    _patch_api(monkeypatch, **kwargs)

    github_triage.import_findings(project)

    items_by_id = {it["id"]: it for it in read_all_items(project)}
    # Failed-source legacy item stays open
    assert items_by_id[legacy_id]["status"] == "triage", (
        f"legacy item for failed source {failed_source} must NOT be migrated"
    )
    # The other three source's legacy items migrate
    for other_id in other_ids:
        assert items_by_id[other_id]["status"] == "dismissed"
        assert items_by_id[other_id]["statusReason"] == "schemaMigration"


# ---------------------------------------------------------------------------
# Code review MED #1 — security action-unit emit gate symmetric with resolve
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cs,db",
    [
        (None, []),
        ([], None),
        (None, [DB_CRITICAL]),
        ([CS_HIGH], None),
    ],
    ids=[
        "cs_failed_db_empty",
        "cs_empty_db_failed",
        "cs_failed_db_has_findings",
        "cs_has_findings_db_failed",
    ],
)
def test_security_emit_requires_both_feeds_succeeded(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    cs,
    db,
) -> None:
    """A partial fetch must NOT emit a security action-unit — the payload
    is frozen at first append and would misleadingly report '0 X alerts'
    for whichever feed failed. Symmetric with the resolve gate."""
    _patch_api(monkeypatch, code_scanning=cs, dependabot=db,
               secret_scanning=[], runs=[])
    github_triage.import_findings(project)
    keys = {e["dedupKey"] for e in _append_events(project)}
    assert "gh-security:acme/foo" not in keys


def test_security_partial_fetch_does_not_resolve_existing_item(
    project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror of the emit gate — a partial fetch also must not resolve.

    Seed an open `gh-security:` item from a prior fully-successful run;
    then a partial fetch must leave it open (not mass-resolve).
    """
    _patch_api(monkeypatch, code_scanning=[CS_HIGH], dependabot=[DB_CRITICAL],
               secret_scanning=[], runs=[])
    github_triage.import_findings(project)
    # Now dependabot fails on the next run.
    _patch_api(monkeypatch, code_scanning=[], dependabot=None,
               secret_scanning=[], runs=[])
    result = github_triage.import_findings(project)
    assert result["resolved"] == 0
    item = next(
        i for i in read_all_items(project)
        if i.get("dedupKey") == "gh-security:acme/foo"
    )
    assert item["status"] == "triage"


def test_legacy_migration_leaves_non_github_items_untouched(
    project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A drift / phaseQuality item with `source != "github"` is untouched even
    if a github fetch succeeds.
    """
    drift_id = append_triage_item(
        project, source="drift", severity="medium", kind="maintenance",
        title="t", detail="d", dedup_key="drift:CLAUDE.md:content",
    )
    github_legacy_id = _seed_legacy_item(project, "github:code-scanning:42")

    _patch_api(
        monkeypatch, code_scanning=[], dependabot=[], secret_scanning=[], runs=[],
    )
    github_triage.import_findings(project)

    items_by_id = {it["id"]: it for it in read_all_items(project)}
    assert items_by_id[drift_id]["status"] == "triage"  # untouched
    assert items_by_id[github_legacy_id]["status"] == "dismissed"

"""gh-pr-ci producer tests — failed hard-gates on OPEN PRs → triage.

iterate-2026-06-11-automerge-gh-pr-ci-producer (B4.5 loop-closing). Covers the
new ``github_pr_api`` fetch/reduce layer, the ``pr_ci_action_unit`` mapper, the
differentiated ``resolve_pr_ci`` auto-resolve, and the ``import_findings``
consumer wiring. Hermetic — the conftest autouse fixture neutralises live PR
fetchers; every test here re-stubs them explicitly.
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
import github_pr_api  # noqa: E402
import github_triage  # noqa: E402
from triage import append_triage_item, read_all_items  # noqa: E402

OWNER_REPO = "acme/foo"

# The conftest autouse fixture (_isolate_github_pr_api) replaces these module
# attributes with no-op stubs. Capture the REAL functions at import (before any
# test runs) so the fetch-level unit tests can opt back in via `real_pr_api`.
_REAL_FETCH_OPEN_PRS = github_pr_api.fetch_open_prs
_REAL_FETCH_PR_CHECK_RUNS = github_pr_api.fetch_pr_check_runs
_REAL_FETCH_PR_STATE = github_pr_api.fetch_pr_state


@pytest.fixture
def real_pr_api(monkeypatch):
    """Undo the autouse hermetic stub so a test exercises the REAL fetch impls
    (which then read the test-patched github_api._gh_api)."""
    monkeypatch.setattr(github_pr_api, "fetch_open_prs", _REAL_FETCH_OPEN_PRS)
    monkeypatch.setattr(
        github_pr_api, "fetch_pr_check_runs", _REAL_FETCH_PR_CHECK_RUNS)
    monkeypatch.setattr(github_pr_api, "fetch_pr_state", _REAL_FETCH_PR_STATE)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _pr(number: int, *, draft: bool = False, branch: str = "feature",
        title: str = "a title") -> dict:
    return {
        "number": number,
        "draft": draft,
        "title": title,
        "html_url": f"https://github.com/acme/foo/pull/{number}",
        "head": {"sha": f"sha{number}", "ref": branch},
    }


def _check(name: str, conclusion: str | None, status: str = "completed") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion}


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


def _patch_pr_api(monkeypatch, *, open_prs, check_runs_by_sha, pr_state=None):
    """Stub the github_pr_api fetch layer + the rest of github_api for a clean
    consumer run (only the PR-CI source is active)."""
    monkeypatch.setattr(github_api, "gh_available", lambda: True)
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    monkeypatch.setattr(github_api, "owner_repo", lambda _: OWNER_REPO)
    monkeypatch.setattr(github_api, "fetch_code_scanning_alerts", lambda: [])
    monkeypatch.setattr(github_api, "fetch_dependabot_alerts", lambda: [])
    monkeypatch.setattr(github_api, "fetch_secret_scanning_alerts", lambda: [])
    monkeypatch.setattr(github_api, "fetch_workflow_runs", lambda b: [])
    monkeypatch.setattr(github_api, "latest_security_workflow_run", lambda: None)
    monkeypatch.setattr(github_api, "download_security_findings", lambda rid, workflow_base=None: None)
    monkeypatch.setattr(github_pr_api, "fetch_open_prs", lambda: open_prs)
    monkeypatch.setattr(
        github_pr_api, "fetch_pr_check_runs",
        lambda head_sha: check_runs_by_sha.get(head_sha),
    )
    monkeypatch.setattr(
        github_pr_api, "fetch_pr_state",
        lambda pr_number: (pr_state or {}).get(pr_number),
    )


# --------------------------------------------------------------------------- #
# _failing_check_names — pure classifier (AC-2)
# --------------------------------------------------------------------------- #
def test_failing_set_includes_all_non_passing_terminal_conclusions() -> None:
    runs = [
        _check("a", "failure"), _check("b", "timed_out"),
        _check("c", "startup_failure"), _check("d", "cancelled"),
        _check("e", "action_required"),
    ]
    assert github_pr_api._failing_check_names(runs) == [
        "a", "b", "c", "d", "e",
    ]


def test_failing_set_excludes_success_neutral_skipped_and_inprogress() -> None:
    runs = [
        _check("ok", "success"), _check("neutral", "neutral"),
        _check("skip", "skipped"), _check("pending", None, status="in_progress"),
        _check("queued", None, status="queued"),
        # a completed failure that SHOULD count, to prove the filter is real
        _check("bad", "failure"),
    ]
    assert github_pr_api._failing_check_names(runs) == ["bad"]


def test_failing_set_is_sorted_deduped_and_sanitised() -> None:
    runs = [
        _check("zeta", "failure"), _check("alpha", "failure"),
        _check("alpha", "failure"),  # duplicate name
        _check("line\nbreak\tinjection", "failure"),  # control chars
    ]
    names = github_pr_api._failing_check_names(runs)
    assert names == sorted(names)  # deterministic order
    assert names.count("alpha") == 1  # deduped
    # control characters collapsed to spaces — no raw newline/tab survives
    assert all("\n" not in n and "\t" not in n for n in names)


# --------------------------------------------------------------------------- #
# fetch helpers — None-on-failure + object/array extraction
# --------------------------------------------------------------------------- #
def test_fetch_open_prs_returns_list_or_none(real_pr_api, monkeypatch) -> None:
    monkeypatch.setattr(github_api, "_gh_api", lambda path, paginate=False: [_pr(1)])
    assert github_pr_api.fetch_open_prs() == [_pr(1)]
    monkeypatch.setattr(github_api, "_gh_api", lambda path, paginate=False: None)
    assert github_pr_api.fetch_open_prs() is None
    monkeypatch.setattr(github_api, "_gh_api", lambda path, paginate=False: {"x": 1})
    assert github_pr_api.fetch_open_prs() is None  # non-list → None


def test_fetch_pr_check_runs_extracts_check_runs(real_pr_api, monkeypatch) -> None:
    payload = {"total_count": 2, "check_runs": [_check("a", "failure"),
                                                _check("b", "success")]}
    monkeypatch.setattr(github_api, "_gh_api", lambda path, paginate=False: payload)
    assert github_pr_api.fetch_pr_check_runs("sha1") == payload["check_runs"]


def test_fetch_pr_check_runs_truncation_guard_returns_none(real_pr_api, monkeypatch) -> None:
    """len(check_runs) < total_count → response truncated → None (symmetry skip),
    so a failing check on an unseen page can never be misread as 'all green'."""
    payload = {"total_count": 150, "check_runs": [_check("a", "success")]}
    monkeypatch.setattr(github_api, "_gh_api", lambda path, paginate=False: payload)
    assert github_pr_api.fetch_pr_check_runs("sha1") is None


def test_fetch_pr_check_runs_none_on_bad_shape(real_pr_api, monkeypatch) -> None:
    monkeypatch.setattr(github_api, "_gh_api", lambda path, paginate=False: None)
    assert github_pr_api.fetch_pr_check_runs("sha1") is None
    monkeypatch.setattr(github_api, "_gh_api", lambda path, paginate=False: [1, 2])
    assert github_pr_api.fetch_pr_check_runs("sha1") is None  # not a dict


def test_fetch_queries_use_safe_filters(real_pr_api, monkeypatch) -> None:
    """The open-PR query is scoped to state=open and check-runs to filter=latest
    (so a re-run-green check never lingers as a stale failed run)."""
    seen: list[str] = []

    def _capture(path, paginate=False):
        seen.append(path)
        return {"total_count": 0, "check_runs": []}

    monkeypatch.setattr(github_api, "_gh_api", _capture)
    github_pr_api.fetch_pr_check_runs("deadbeef")
    assert "filter=latest" in seen[-1]
    monkeypatch.setattr(github_api, "_gh_api", lambda path, paginate=False: seen.append(path) or [])
    github_pr_api.fetch_open_prs()
    assert "state=open" in seen[-1]


def test_fetch_pr_state_extracts_state_and_merged(real_pr_api, monkeypatch) -> None:
    monkeypatch.setattr(
        github_api, "_gh_api",
        lambda path, paginate=False: {"state": "closed", "merged": True, "x": 9},
    )
    assert github_pr_api.fetch_pr_state(7) == {"state": "closed", "merged": True}
    monkeypatch.setattr(github_api, "_gh_api", lambda path, paginate=False: None)
    assert github_pr_api.fetch_pr_state(7) is None


# --------------------------------------------------------------------------- #
# open_prs_with_failed_checks — reduce + symmetry + draft exclusion
# --------------------------------------------------------------------------- #
def test_reduce_none_input_returns_none(monkeypatch) -> None:
    assert github_pr_api.open_prs_with_failed_checks(None) is None


def test_reduce_keeps_only_prs_with_failing_checks(monkeypatch) -> None:
    monkeypatch.setattr(github_pr_api, "fetch_pr_check_runs", lambda sha: {
        "sha1": [_check("ci", "failure")],
        "sha2": [_check("ci", "success")],
    }[sha])
    out = github_pr_api.open_prs_with_failed_checks([_pr(1), _pr(2)])
    assert [p["number"] for p in out] == [1]
    assert out[0]["failing_checks"] == ["ci"]


def test_reduce_excludes_draft_prs(monkeypatch) -> None:
    monkeypatch.setattr(
        github_pr_api, "fetch_pr_check_runs",
        lambda sha: [_check("ci", "failure")],
    )
    out = github_pr_api.open_prs_with_failed_checks(
        [_pr(1, draft=True), _pr(2)]
    )
    assert [p["number"] for p in out] == [2]  # draft #1 skipped


def test_reduce_symmetry_any_none_fetch_returns_none(monkeypatch) -> None:
    """A single failed per-PR check fetch poisons the whole sweep (AC-3) —
    prevents a network blip from false-resolving every gh-pr-ci item."""
    monkeypatch.setattr(github_pr_api, "fetch_pr_check_runs", lambda sha: {
        "sha1": [_check("ci", "failure")],
        "sha2": None,  # transient failure
    }[sha])
    assert github_pr_api.open_prs_with_failed_checks([_pr(1), _pr(2)]) is None


# --------------------------------------------------------------------------- #
# pr_ci_action_unit — mapper (AC-1)
# --------------------------------------------------------------------------- #
def _pr_info(number=5, failing=("CI", "Lint")):
    return {
        "number": number, "html_url": f"https://github.com/acme/foo/pull/{number}",
        "title": "fix things", "head_branch": "feature",
        "failing_checks": list(failing),
    }


def test_pr_ci_action_unit_shape() -> None:
    unit = github_triage.pr_ci_action_unit(_pr_info(), owner_repo=OWNER_REPO)
    assert unit["dedup_key"] == "gh-pr-ci:5"
    assert unit["severity"] == "high"
    assert unit["kind"] == "bug"
    payload = unit["launch_payload"]
    assert payload.startswith("/shipwright-iterate --type bug")
    assert "https://github.com/acme/foo/pull/5" in payload
    assert "CI" in payload and "Lint" in payload
    assert "gh-pr-ci:5" in payload  # provenance


def test_pr_ci_action_unit_payload_deterministic() -> None:
    # Differently-ordered (and duplicated) input must yield a byte-identical
    # payload — determinism is intrinsic to the mapper, not the caller (LOW-1).
    a = github_triage.pr_ci_action_unit(
        _pr_info(failing=["Lint", "CI", "CI"]), owner_repo=OWNER_REPO)
    b = github_triage.pr_ci_action_unit(
        _pr_info(failing=["CI", "Lint"]), owner_repo=OWNER_REPO)
    assert a["launch_payload"] == b["launch_payload"]
    assert a["detail"] == b["detail"]


def test_pr_ci_action_unit_none_without_number() -> None:
    assert github_triage.pr_ci_action_unit(
        {"failing_checks": ["x"]}, owner_repo=OWNER_REPO) is None


# --------------------------------------------------------------------------- #
# Consumer integration — emit / idempotency / round-trip / wiring
# --------------------------------------------------------------------------- #
def test_import_emits_pr_ci_action_unit(tmp_path, monkeypatch) -> None:
    _patch_pr_api(
        monkeypatch, open_prs=[_pr(7)],
        check_runs_by_sha={"sha7": [_check("CI", "failure")]},
    )
    result = github_triage.import_findings(tmp_path)
    assert result["by_source"][github_triage.PREFIX_PR_CI] == 1
    keys = {e["dedupKey"] for e in _append_events(tmp_path)}
    assert "gh-pr-ci:7" in keys


def test_import_pr_ci_roundtrips_through_triage_jsonl(tmp_path, monkeypatch) -> None:
    """AC-6: the action-unit survives write→read through triage.jsonl intact."""
    _patch_pr_api(
        monkeypatch, open_prs=[_pr(7)],
        check_runs_by_sha={"sha7": [_check("CI", "failure")]},
    )
    github_triage.import_findings(tmp_path)
    item = next(i for i in read_all_items(tmp_path)
                if i.get("dedupKey") == "gh-pr-ci:7")
    assert item["severity"] == "high"
    assert item["kind"] == "bug"
    assert item["launchPayload"].startswith("/shipwright-iterate --type bug")


def test_import_pr_ci_idempotent(tmp_path, monkeypatch) -> None:
    _patch_pr_api(
        monkeypatch, open_prs=[_pr(7)],
        check_runs_by_sha={"sha7": [_check("CI", "failure")]},
    )
    first = github_triage.import_findings(tmp_path)
    second = github_triage.import_findings(tmp_path)
    assert first["by_source"][github_triage.PREFIX_PR_CI] == 1
    assert second["by_source"][github_triage.PREFIX_PR_CI] == 0
    assert len([e for e in _append_events(tmp_path)
                if e["dedupKey"] == "gh-pr-ci:7"]) == 1


def test_import_pr_ci_symmetry_none_fetch_marks_by_source_none(tmp_path, monkeypatch) -> None:
    _patch_pr_api(monkeypatch, open_prs=None, check_runs_by_sha={})
    result = github_triage.import_findings(tmp_path)
    assert result["by_source"][github_triage.PREFIX_PR_CI] is None


def test_import_findings_actually_calls_pr_api(tmp_path, monkeypatch) -> None:
    """Wiring guard (external-review #11): the hermetic autouse stub must not
    hide a broken production wire — assert import_findings really reaches
    github_pr_api.fetch_open_prs."""
    called = {"n": 0}

    def _spy():
        called["n"] += 1
        return []

    _patch_pr_api(monkeypatch, open_prs=[], check_runs_by_sha={})
    monkeypatch.setattr(github_pr_api, "fetch_open_prs", _spy)
    github_triage.import_findings(tmp_path)
    assert called["n"] == 1


# --------------------------------------------------------------------------- #
# Differentiated auto-resolve (AC-4)
# --------------------------------------------------------------------------- #
def _seed_pr_ci(project, number) -> str:
    return append_triage_item(
        project, source="github", severity="high", kind="bug",
        title=f"PR #{number}", detail="d", dedup_key=f"gh-pr-ci:{number}",
    )


def test_resolve_pr_checks_went_green(tmp_path, monkeypatch) -> None:
    item_id = _seed_pr_ci(tmp_path, 7)
    # PR #7 still open, but now all checks pass → no failing PRs.
    _patch_pr_api(
        monkeypatch, open_prs=[_pr(7)],
        check_runs_by_sha={"sha7": [_check("CI", "success")]},
    )
    github_triage.import_findings(tmp_path)
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["status"] == "dismissed"
    assert item["statusReason"] == "prChecksResolved"


def test_resolve_pr_merged_and_closed(tmp_path, monkeypatch) -> None:
    merged_id = _seed_pr_ci(tmp_path, 7)
    closed_id = _seed_pr_ci(tmp_path, 8)
    # Neither PR is open anymore; state fetch distinguishes merged vs closed.
    _patch_pr_api(
        monkeypatch, open_prs=[], check_runs_by_sha={},
        pr_state={7: {"state": "closed", "merged": True},
                  8: {"state": "closed", "merged": False}},
    )
    github_triage.import_findings(tmp_path)
    by_id = {i["id"]: i for i in read_all_items(tmp_path)}
    assert by_id[merged_id]["statusReason"] == "prMerged"
    assert by_id[closed_id]["statusReason"] == "prClosed"


def test_resolve_keeps_item_open_when_state_unfetchable(tmp_path, monkeypatch) -> None:
    """Refinement #4: a gone-from-open PR whose state fetch fails is NOT guessed
    as prClosed — kept open, resolved a later cycle. Prevents mis-resolving a
    still-open PR omitted by an incomplete open-set fetch."""
    item_id = _seed_pr_ci(tmp_path, 7)
    _patch_pr_api(
        monkeypatch, open_prs=[], check_runs_by_sha={},
        pr_state={7: None},  # state fetch failed
    )
    github_triage.import_findings(tmp_path)
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["status"] == "triage"


def test_partial_fetch_does_not_resolve_existing_pr_ci_item(tmp_path, monkeypatch) -> None:
    """AC-3 resolve half: a poisoned sweep (one check fetch None) leaves a
    previously-emitted gh-pr-ci item untouched."""
    item_id = _seed_pr_ci(tmp_path, 7)
    _patch_pr_api(
        monkeypatch, open_prs=[_pr(7), _pr(8)],
        check_runs_by_sha={"sha7": [_check("CI", "success")], "sha8": None},
    )
    result = github_triage.import_findings(tmp_path)
    assert result["by_source"][github_triage.PREFIX_PR_CI] is None
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["status"] == "triage"


def test_generic_resolve_stale_skips_pr_ci(tmp_path, monkeypatch) -> None:
    """External-review #12: gh-pr-ci items are resolved ONLY by resolve_pr_ci,
    never by the generic gh-security/gh-ci sweep. Seed an open gh-pr-ci item and
    a successful non-PR run; the generic sweep must leave it alone (the PR-CI
    path keeps it because it's still failing)."""
    item_id = _seed_pr_ci(tmp_path, 7)
    _patch_pr_api(
        monkeypatch, open_prs=[_pr(7)],
        check_runs_by_sha={"sha7": [_check("CI", "failure")]},
    )
    github_triage.import_findings(tmp_path)
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["status"] == "triage"  # still failing → not resolved

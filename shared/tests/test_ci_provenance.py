"""Tests for shared/scripts/ci_provenance.py — resolve_ci_verification().

P3.4c (iterate-2026-09-08-ci-provenance-attestation). Every test monkeypatches
the `gh`-subprocess seam (`ci_provenance._gh_api`, module-object level per
ADR-045 convention) — never the real GitHub API — and `github_api.owner_repo`.
No test reads or writes any local file: the whole point of this predicate is
that it never consults the local tree for its verdict (AC3/AC8).

`_gh_api()`'s own subprocess-level tests live in test_ci_provenance_gh_api.py;
exact-commit binding, OS-matrix scanning, and input/truncation hardening
tests live in test_ci_provenance_hardening.py (both split out once this file
crossed the 300-line guideline).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import ci_provenance  # noqa: E402
import github_api  # noqa: E402

_COMMIT = "a" * 40
_OWNER, _REPO = "acme", "foo"
_DEFAULT_BRANCH = "main"


def _repo_endpoint(owner: str, repo: str) -> str:
    return f"repos/{owner}/{repo}"


def _runs_endpoint(owner: str, repo: str) -> str:
    return f"repos/{owner}/{repo}/actions/workflows/ci.yml/runs"


def _jobs_endpoint(owner: str, repo: str, run_id: int) -> str:
    return f"repos/{owner}/{repo}/actions/runs/{run_id}/jobs"


def _run(run_id: int, *, event="push", head_branch=_DEFAULT_BRANCH, conclusion="success", started="2026-09-08T10:00:00Z"):
    return {
        "id": run_id,
        "event": event,
        "head_branch": head_branch,
        "conclusion": conclusion,
        "run_started_at": started,
    }


def _jobs_with_step(conclusion: str | None):
    steps = []
    if conclusion is not None:
        steps.append({"name": ci_provenance.PROVENANCE_STEP_NAME, "conclusion": conclusion})
    return {"jobs": [{"steps": steps}]}


@pytest.fixture(autouse=True)
def _fixed_owner_repo(monkeypatch):
    monkeypatch.setattr(github_api, "owner_repo", lambda project_root: f"{_OWNER}/{_REPO}")


def _install_gh_api(monkeypatch, *, runs: list[dict], jobs_by_run: dict[int, dict], commit: str = _COMMIT):
    """Scripted `_gh_api` dispatch keyed on the endpoint path prefix. The runs
    endpoint only answers when the query string actually pins `head_sha` to
    `commit` — a query missing that binding is exactly the bug class that
    would let this predicate answer about *any* recent trunk run instead of
    the one commit it was asked about (code-reviewer finding)."""

    def fake_gh_api(path: str, *, cwd):
        if path.startswith(_repo_endpoint(_OWNER, _REPO)) and "/actions/" not in path:
            return {"default_branch": _DEFAULT_BRANCH}
        if path.startswith(_runs_endpoint(_OWNER, _REPO)):
            if f"head_sha={commit}" not in path or "per_page=100" not in path:
                return {"workflow_runs": []}
            return {"workflow_runs": runs}
        for run_id, payload in jobs_by_run.items():
            if path.startswith(_jobs_endpoint(_OWNER, _REPO, run_id)):
                return payload
        return None

    monkeypatch.setattr(ci_provenance, "_gh_api", fake_gh_api)


def test_verified_when_qualifying_run_confirms_clean_manifest(monkeypatch, tmp_path):
    _install_gh_api(
        monkeypatch,
        runs=[_run(101)],
        jobs_by_run={101: _jobs_with_step("success")},
    )
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "verified"
    assert result.run_id == 101


def test_not_verified_when_qualifying_run_never_confirms(monkeypatch, tmp_path):
    _install_gh_api(
        monkeypatch,
        runs=[_run(101)],
        jobs_by_run={101: _jobs_with_step("skipped")},
    )
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "not_verified"


def test_no_record_when_no_run_matches_head_sha(monkeypatch, tmp_path):
    _install_gh_api(monkeypatch, runs=[], jobs_by_run={})
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "no_record"


def test_no_record_when_only_pull_request_runs_exist(monkeypatch, tmp_path):
    """AC8 — the actual forgery vector: a PR's own (possibly attacker-modified)
    ci.yml runs before human review, so a pull_request-triggered run must
    never count, even when its step conclusion reads 'success'."""
    _install_gh_api(
        monkeypatch,
        runs=[_run(202, event="pull_request")],
        jobs_by_run={202: _jobs_with_step("success")},
    )
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "no_record"


def test_no_record_when_run_is_on_a_non_default_branch(monkeypatch, tmp_path):
    _install_gh_api(
        monkeypatch,
        runs=[_run(203, head_branch="feature/x")],
        jobs_by_run={203: _jobs_with_step("success")},
    )
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "no_record"


def test_no_record_when_run_conclusion_is_not_success(monkeypatch, tmp_path):
    _install_gh_api(
        monkeypatch,
        runs=[_run(204, conclusion="failure")],
        jobs_by_run={204: _jobs_with_step("success")},
    )
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "no_record"


def test_verified_searches_past_a_non_confirming_newer_run(monkeypatch, tmp_path):
    """AC9 — multi-run search: a later rerun without a confirming step
    conclusion must not hide an earlier genuine pass for the same commit."""
    _install_gh_api(
        monkeypatch,
        runs=[
            _run(301, started="2026-09-08T12:00:00Z"),  # newest, not confirmed
            _run(300, started="2026-09-08T10:00:00Z"),  # older, confirmed
        ],
        jobs_by_run={
            301: _jobs_with_step("skipped"),
            300: _jobs_with_step("success"),
        },
    )
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "verified"
    assert result.run_id == 300


def test_local_file_forgery_is_never_consulted(monkeypatch, tmp_path):
    """AC3 — a fabricated local record at a path a naive implementation might
    read must have zero effect: the predicate never opens any local file."""
    fake = tmp_path / ".ci-junit" / "ci-provenance.json"
    fake.parent.mkdir(parents=True)
    fake.write_text(
        '{"commit": "' + _COMMIT + '", "status": "verified"}', encoding="utf-8"
    )
    _install_gh_api(monkeypatch, runs=[], jobs_by_run={})
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "no_record"


def test_error_on_invalid_commit_shape(tmp_path):
    result = ci_provenance.resolve_ci_verification("not-a-sha!", project_root=tmp_path)
    assert result.status == "error"


def test_error_when_owner_repo_unresolvable(monkeypatch, tmp_path):
    monkeypatch.setattr(github_api, "owner_repo", lambda project_root: None)
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "error"


def test_error_when_gh_transport_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(ci_provenance, "_gh_api", lambda path, *, cwd: None)
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "error"


def test_error_when_jobs_query_fails_for_a_qualifying_run(monkeypatch, tmp_path):
    """Stage-1 spec review: a jobs-API failure (transient `gh` error, timeout,
    malformed JSON) for an otherwise-qualifying run must map to `error`, never
    fall through to `not_verified` — the two facts ("nobody confirmed it" vs
    "we could not ask") must never be conflated."""

    def fake_gh_api(path: str, *, cwd):
        if "/actions/" not in path:
            return {"default_branch": _DEFAULT_BRANCH}
        if "/runs?" in path:
            return {"workflow_runs": [_run(101)]}
        return None  # the jobs-endpoint query itself fails

    monkeypatch.setattr(ci_provenance, "_gh_api", fake_gh_api)
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "error"


#: `_gh_api()`'s own subprocess construction, transport-failure and
#: cwd-binding coverage lives in test_ci_provenance_gh_api.py; exact-commit
#: query binding, OS-matrix job scanning, a genuinely-absent provenance
#: step, and input/truncation hardening live in
#: test_ci_provenance_hardening.py (both split out once this file crossed
#: the 300-line guideline).

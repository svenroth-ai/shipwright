"""Hardening tests for shared/scripts/ci_provenance.py — split out of
test_ci_provenance.py (P3.4c, iterate-2026-09-08-ci-provenance-attestation)
once that file crossed the 300-line guideline. test_ci_provenance.py covers
the four core outcomes (verified/not_verified/no_record/error) and the
forgery vectors (AC3/AC8); this file covers the edge cases Stage-3 doubt
review and code-reviewer surfaced afterward: exact-commit binding, OS-matrix
job scanning, a genuinely-absent provenance step, and the input/truncation
hardening (abbreviated commit, invalid `workflow_file`, truncated runs page).
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
    def fake_gh_api(path: str, *, cwd):
        if path.startswith(f"repos/{_OWNER}/{_REPO}") and "/actions/" not in path:
            return {"default_branch": _DEFAULT_BRANCH}
        if path.startswith(f"repos/{_OWNER}/{_REPO}/actions/workflows/ci.yml/runs"):
            if f"head_sha={commit}" not in path or "per_page=100" not in path:
                return {"workflow_runs": []}
            return {"workflow_runs": runs}
        for run_id, payload in jobs_by_run.items():
            if path.startswith(_jobs_endpoint(_OWNER, _REPO, run_id)):
                return payload
        return None

    monkeypatch.setattr(ci_provenance, "_gh_api", fake_gh_api)


def test_error_on_abbreviated_commit_never_falls_through_to_no_record(monkeypatch, tmp_path):
    """Stage-3 doubt review: GitHub's `head_sha` filter is an exact 40-char
    match, so a library caller passing a 7-39 char abbreviation (the CLI
    wrapper expands via `git rev-parse`, but this function is the actual
    library surface P3.5 calls directly) must get `error` ('cannot answer'),
    never a false `no_record` ('definitely never ran')."""
    _install_gh_api(monkeypatch, runs=[_run(101)], jobs_by_run={101: _jobs_with_step("success")})
    result = ci_provenance.resolve_ci_verification(_COMMIT[:12], project_root=tmp_path)
    assert result.status == "error"


def test_error_on_invalid_workflow_file(tmp_path):
    """The `workflow_file` keyword lands in the same request path as
    `commit`; unlike `commit` it was previously unvalidated."""
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path, workflow_file="../secrets")
    assert result.status == "error"


def test_error_when_runs_response_is_truncated(monkeypatch, tmp_path):
    """`total_count` exceeding the fetched page means the runs list was
    silently truncated — GitHub returns newest-first, so the truncated tail
    is the OLDEST runs, exactly where an older confirming run could live.
    Must report `error`, never a false `not_verified`."""

    def fake_gh_api(path: str, *, cwd):
        if "/actions/" not in path:
            return {"default_branch": _DEFAULT_BRANCH}
        if "/runs?" in path:
            return {"workflow_runs": [_run(101)], "total_count": 250}
        return {"jobs": [{"steps": []}]}

    monkeypatch.setattr(ci_provenance, "_gh_api", fake_gh_api)
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "error"


def test_runs_query_is_bound_to_this_exact_commit(monkeypatch, tmp_path):
    """A qualifying run for a DIFFERENT commit must never leak into this
    commit's result — this is the actual binding the Round-3 'head_sha
    already pins run->commit->manifest' argument rests on."""
    _install_gh_api(
        monkeypatch,
        runs=[_run(101)],
        jobs_by_run={101: _jobs_with_step("success")},
        commit="f" * 40,  # a different commit's runs are all that's scripted
    )
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "no_record"


def test_not_verified_when_provenance_step_is_absent_from_run(monkeypatch, tmp_path):
    """A run that predates this feature (every historical run on `main`) has
    no `PROVENANCE_STEP_NAME` step at all — `_jobs_with_step(None)` models
    exactly that: the step is genuinely absent, not merely non-successful."""
    _install_gh_api(
        monkeypatch,
        runs=[_run(101)],
        jobs_by_run={101: _jobs_with_step(None)},
    )
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "not_verified"


def test_error_when_jobs_response_has_malformed_step_shape(monkeypatch, tmp_path):
    """External code review (openai): a schema-malformed job entry (`steps`
    not a list) must not be silently read as 'the step is absent' — that
    conflates a malformed API response with a genuine negative, the same
    conflation class Stage 1 already caught once at the run level."""

    def fake_gh_api(path: str, *, cwd):
        if "/actions/" not in path:
            return {"default_branch": _DEFAULT_BRANCH}
        if "/runs?" in path:
            return {"workflow_runs": [_run(101)]}
        if path.startswith(_jobs_endpoint(_OWNER, _REPO, 101)):
            return {"jobs": [{"steps": "not-a-list"}]}
        return None

    monkeypatch.setattr(ci_provenance, "_gh_api", fake_gh_api)
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "error"


def test_malformed_job_does_not_hide_a_confirming_job(monkeypatch, tmp_path):
    """A malformed job entry alongside a genuinely confirming one must still
    report `verified` — the permissive any-job-confirms reading takes
    priority over reporting the malformed sibling."""

    def fake_gh_api(path: str, *, cwd):
        if "/actions/" not in path:
            return {"default_branch": _DEFAULT_BRANCH}
        if "/runs?" in path:
            return {"workflow_runs": [_run(101)]}
        if path.startswith(_jobs_endpoint(_OWNER, _REPO, 101)):
            return {
                "jobs": [
                    {"steps": "not-a-list"},
                    {"steps": [{"name": ci_provenance.PROVENANCE_STEP_NAME, "conclusion": "success"}]},
                ]
            }
        return None

    monkeypatch.setattr(ci_provenance, "_gh_api", fake_gh_api)
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "verified"


def test_uppercase_commit_is_accepted_via_lowercase_normalization(monkeypatch, tmp_path):
    """External code review (glm): git/GitHub always emit lowercase SHAs, but
    an uppercase 40-char SHA is still a legal commit identity — a direct
    library caller should not be rejected for case alone."""
    _install_gh_api(monkeypatch, runs=[_run(101)], jobs_by_run={101: _jobs_with_step("success")})
    result = ci_provenance.resolve_ci_verification(_COMMIT.upper(), project_root=tmp_path)
    assert result.status == "verified"


def test_verified_when_confirming_step_is_in_a_second_job_of_a_matrixed_run(monkeypatch, tmp_path):
    """If `python-checks` is ever run as an OS matrix, the provenance step
    exists once per matrix leg; ANY leg confirming a clean manifest must
    count, even if an earlier-iterated leg's own copy of the step was
    skipped (job iteration order is not guaranteed)."""

    def fake_gh_api(path: str, *, cwd):
        if "/actions/" not in path:
            return {"default_branch": _DEFAULT_BRANCH}
        if "/runs?" in path:
            return {"workflow_runs": [_run(101)]}
        if path.startswith(_jobs_endpoint(_OWNER, _REPO, 101)):
            return {
                "jobs": [
                    {"steps": [{"name": ci_provenance.PROVENANCE_STEP_NAME, "conclusion": "skipped"}]},
                    {"steps": [{"name": ci_provenance.PROVENANCE_STEP_NAME, "conclusion": "success"}]},
                ]
            }
        return None

    monkeypatch.setattr(ci_provenance, "_gh_api", fake_gh_api)
    result = ci_provenance.resolve_ci_verification(_COMMIT, project_root=tmp_path)
    assert result.status == "verified"
    assert result.run_id == 101

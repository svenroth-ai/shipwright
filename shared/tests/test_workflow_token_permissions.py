"""Least-privilege GITHUB_TOKEN guard for every .github/workflows/*.yml.

Locks in the OpenSSF Scorecard Token-Permissions hardening
(iterate-2026-06-30-workflow-token-permissions): the workflow token must be
read-only at the top level, and a job widens itself ONLY to the exact write
scope it needs. A GitHub Actions job-level ``permissions:`` block REPLACES the
top-level one (it does NOT merge), so a widening job must re-declare every read
scope it still needs (e.g. ``contents: read`` for ``actions/checkout``).

``security.yml`` is the deliberate exception: it is a single-job SARIF workflow
whose top-level block is convention-locked by the compliance A5.3 audit
(``security_workflow.REQUIRED_PERMISSIONS``), which reads the *top-level*
``permissions:``. With one job, top-level == job-level effective scope, so there
is no least-privilege loss. This test pins that exception explicitly so a future
"move it to the job level" edit fails loudly here (and it would also break A5.3).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load(name: str) -> dict:
    path = _WORKFLOWS / name
    assert path.is_file(), f"missing workflow: {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _writes(perms) -> list[str]:
    """Return the keys granted ``write`` in a permissions mapping (empty if read-only)."""
    if not isinstance(perms, dict):
        return []
    return [k for k, v in perms.items() if str(v) == "write"]


# Workflows hardened to a read-only top-level token. security.yml is excluded
# on purpose (see module docstring + the dedicated test below).
_READ_ONLY_TOP = ["ci.yml", "codeql.yml", "bloat-check.yml", "pr-review.yml"]


@pytest.mark.parametrize("name", _READ_ONLY_TOP)
def test_top_level_token_is_read_only(name: str) -> None:
    top = _load(name).get("permissions")
    assert isinstance(top, dict) and top, (
        f"{name}: explicit top-level `permissions:` block missing — implicit "
        f"token permissions are org-policy-dependent."
    )
    assert top.get("contents") == "read", f"{name}: top-level must grant contents:read"
    assert not _writes(top), (
        f"{name}: top-level permissions must stay read-only; write scopes found: "
        f"{_writes(top)} — move them to the job that needs them."
    )


def test_bloat_check_job_widens_to_pr_write() -> None:
    job = (_load("bloat-check.yml").get("jobs") or {}).get("bloat-check") or {}
    perms = job.get("permissions") or {}
    assert perms.get("pull-requests") == "write", (
        "bloat-check job must widen to pull-requests:write for its PR comment"
    )
    assert perms.get("contents") == "read", (
        "job-level block REPLACES top-level — bloat-check must re-declare contents:read"
    )


def test_pr_review_only_review_job_widens() -> None:
    jobs = _load("pr-review.yml").get("jobs") or {}
    review = jobs.get("review") or {}
    rperms = review.get("permissions") or {}
    assert rperms.get("pull-requests") == "write", (
        "pr-review `review` job must widen to pull-requests:write to post the review"
    )
    assert rperms.get("contents") == "read", (
        "job-level block REPLACES top-level — review must re-declare contents:read"
    )
    # The non-posting jobs must NOT carry any write scope (they inherit the
    # read-only top-level, or declare their own read-only block).
    for jname in ("decide", "selftest"):
        job = jobs.get(jname)
        if job is None:
            continue  # selftest exists only in the webui variant
        assert not _writes(job.get("permissions")), (
            f"pr-review `{jname}` job must not hold any write scope"
        )


def test_codeql_analyze_job_has_security_events_write() -> None:
    job = (_load("codeql.yml").get("jobs") or {}).get("analyze") or {}
    perms = job.get("permissions") or {}
    assert perms.get("security-events") == "write", (
        "codeql analyze job needs security-events:write for the SARIF upload"
    )


def test_security_yml_is_the_documented_top_level_exception() -> None:
    # security.yml KEEPS its write scopes at the top level — convention-locked
    # by the compliance A5.3 audit. Asserting it here documents the exception
    # and fails loudly if someone naively "hardens" it and breaks A5.3.
    top = _load("security.yml").get("permissions") or {}
    assert top.get("security-events") == "write"
    assert top.get("actions") == "read"
    assert top.get("contents") == "read"

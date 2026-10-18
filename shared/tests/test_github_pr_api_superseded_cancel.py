"""A concurrency-cancelled check run superseded by a later one is not a failure.

PR #889 / #888 (2026-10-18): Dependabot fires opened/labeled/synchronize in
quick succession, `pr-review.yml`'s `cancel-in-progress` cancels the earlier
`Prepare review request` runs, and `filter=latest` keeps those cancelled runs
beside the green one. The gh-pr-ci producer then raised a card for a green check.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import github_pr_api  # noqa: E402


def _run(name: str, conclusion: str, started_at: str) -> dict:
    return {"name": name, "status": "completed", "conclusion": conclusion,
            "started_at": started_at}


@pytest.mark.covers("FR-01.14/AC05")
def test_cancelled_run_superseded_by_later_run_is_not_failing() -> None:
    runs = [
        _run("Prepare review request", "cancelled", "2026-10-18T03:07:06Z"),
        _run("Prepare review request", "cancelled", "2026-10-18T03:07:07Z"),
        _run("Prepare review request", "success", "2026-10-18T03:07:10Z"),
    ]
    assert github_pr_api._failing_check_names(runs) == []


@pytest.mark.covers("FR-01.14/AC05")
def test_cancelled_run_that_is_the_latest_still_fails() -> None:
    runs = [
        _run("build", "success", "2026-10-18T03:07:06Z"),
        _run("build", "cancelled", "2026-10-18T03:07:10Z"),
    ]
    assert github_pr_api._failing_check_names(runs) == ["build"]


@pytest.mark.covers("FR-01.14/AC05")
def test_real_failure_is_never_masked_by_a_later_same_named_run() -> None:
    runs = [
        _run("build", "failure", "2026-10-18T03:07:06Z"),
        _run("build", "success", "2026-10-18T03:07:10Z"),
    ]
    assert github_pr_api._failing_check_names(runs) == ["build"]


@pytest.mark.covers("FR-01.14/AC05")
def test_cancelled_run_without_started_at_still_counts_as_failing() -> None:
    runs = [
        {"name": "build", "status": "completed", "conclusion": "cancelled"},
        _run("build", "success", "2026-10-18T03:07:10Z"),
        "not-a-dict",
    ]
    assert github_pr_api._failing_check_names(runs) == ["build"]

"""Untrusted text in an action-unit's detail line is length-capped.

iterate-2026-07-27-triage-defer-ci-cap, card ``trg-813d2305`` (REQ-3 Phase 2
walk of FR-01.14, criterion 13). An entry built from a failing check carries
the workflow name, the branch and — for a proposed change — the title whoever
opened it wrote. The security entry capped its detail and the proposed-change
entry capped its detail; the failing-check entry capped only its title, so one
entry could grow without limit and crowd the rest out of a view that shows a
capped number of items.

Control characters are stripped separately, at display, on both surfaces —
this is a crowding guarantee, not an escaping one.

A NEW file rather than an addition to ``test_github_triage_action_units.py``
(baselined at 598 lines) or ``test_github_triage_pr_ci.py`` (420, ADR-101):
appending to either would ratchet the bloat baseline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from github_triage.mappers import (  # noqa: E402
    _DETAIL_MAX_LEN,
    ci_action_unit,
    pr_ci_action_unit,
)

OWNER_REPO = "acme/foo"


def _ci_run(*, name: str = "CI", branch: str = "main", url: str = "u") -> dict:
    return {
        "workflow_id": 42, "name": name, "head_branch": branch,
        "conclusion": "failure", "head_sha": "abc1234def", "html_url": url,
    }


def _pr(*, title: str = "fix things", branch: str = "main") -> dict:
    return {
        "number": 7, "html_url": "https://github.com/acme/foo/pull/7",
        "title": title, "head_branch": branch, "failing_checks": ["ci"],
    }


# ---------------------------------------------------------------------------
# AC-7 — the failing-check entry is capped like its two siblings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["name", "branch", "url"])
def test_failing_check_detail_is_capped_whatever_grows(field: str) -> None:
    unit = ci_action_unit(_ci_run(**{field: "x" * 5000}), owner_repo=OWNER_REPO)
    assert unit is not None
    assert len(unit["detail"]) == _DETAIL_MAX_LEN
    assert unit["detail"].endswith("…")


def test_failing_check_cap_matches_the_proposed_change_cap() -> None:
    """The card's ask in one assertion: the same cap, not merely *a* cap."""
    ci = ci_action_unit(_ci_run(name="n" * 5000), owner_repo=OWNER_REPO)
    pr = pr_ci_action_unit(_pr(title="t" * 5000), owner_repo=OWNER_REPO)
    assert len(ci["detail"]) == len(pr["detail"]) == _DETAIL_MAX_LEN


def test_capping_the_detail_leaves_the_title_cap_alone() -> None:
    unit = ci_action_unit(_ci_run(name="n" * 5000), owner_repo=OWNER_REPO)
    assert len(unit["title"]) == 160


# ---------------------------------------------------------------------------
# AC-8 — only what exceeds the cap is truncated
# ---------------------------------------------------------------------------

def _pad_ci_detail_to(target: int) -> dict:
    """Build a run whose composed detail is exactly ``target`` characters.

    Measured against a one-character workflow name rather than an empty one:
    the mapper falls back to ``"workflow"`` when the name is falsy, which
    would silently shift the arithmetic by eight.
    """
    probe = ci_action_unit(_ci_run(name="n"), owner_repo=OWNER_REPO)
    return _ci_run(name="n" * (target - len(probe["detail"]) + 1))


@pytest.mark.parametrize(
    "length,expect_truncated",
    [(_DETAIL_MAX_LEN - 1, False), (_DETAIL_MAX_LEN, False),
     (_DETAIL_MAX_LEN + 1, True)],
)
def test_failing_check_detail_boundary(length: int, expect_truncated: bool) -> None:
    unit = ci_action_unit(_pad_ci_detail_to(length), owner_repo=OWNER_REPO)
    assert unit["detail"].endswith("…") is expect_truncated
    assert len(unit["detail"]) == min(length, _DETAIL_MAX_LEN)


def _pad_pr_detail_to(target: int) -> dict:
    probe = pr_ci_action_unit(_pr(title="t"), owner_repo=OWNER_REPO)
    return _pr(title="t" * (target - len(probe["detail"]) + 1))


@pytest.mark.parametrize(
    "length,expect_truncated",
    [(_DETAIL_MAX_LEN - 1, False), (_DETAIL_MAX_LEN, False),
     (_DETAIL_MAX_LEN + 1, True)],
)
def test_proposed_change_detail_boundary(length: int, expect_truncated: bool) -> None:
    """The sibling's boundary, so `>=` cannot creep in on either side."""
    unit = pr_ci_action_unit(_pad_pr_detail_to(length), owner_repo=OWNER_REPO)
    assert unit["detail"].endswith("…") is expect_truncated
    assert len(unit["detail"]) == min(length, _DETAIL_MAX_LEN)


def test_an_ordinary_failing_check_detail_is_untouched() -> None:
    unit = ci_action_unit(
        _ci_run(name="CI", branch="main", url="https://example.test/1"),
        owner_repo=OWNER_REPO,
    )
    assert unit["detail"] == (
        "Workflow 'CI' last concluded 'failure' on main@abc1234 "
        "| latest run: https://example.test/1"
    )


def test_an_ordinary_proposed_change_detail_is_untouched() -> None:
    unit = pr_ci_action_unit(_pr(), owner_repo=OWNER_REPO)
    assert unit["detail"] == (
        'PR #7 "fix things" on main | failing checks: ci '
        "| https://github.com/acme/foo/pull/7"
    )

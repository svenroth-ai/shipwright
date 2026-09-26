"""Prose guards for campaign-dag-scheduler R5b's rebase cascade (3f-bis) --
specifically the `ensure_current.py` exit-code handling added in round 17,
split out from `test_campaign_r5b_merge_lane_prose.py` when that file crossed
the 300-line guideline (same reason `test_campaign_r5b_merge_lane_prose_drain.py`
was split out in round 2), and reusing its harness.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _campaign_prose_harness import step_3f_bis as _step_3f_bis  # noqa: E402


def test_ensure_current_failure_captures_the_real_exit_code():
    """Tier-3 review, R5b round 17, blocking: a prior draft branched on
    `ensure_current.py`'s bare success/failure (`if guard=$(...); then ...
    else ...`), so every nonzero exit fell into the same branch -- the exit
    code itself must be captured so later branches can tell them apart."""
    step = _step_3f_bis()
    assert "ensure_current_rc=$?" in step


def test_ensure_current_exit_2_is_the_only_path_to_rebase_conflict():
    """Only ensure_current.py's own exit code 2 (its `blocked` status: a
    confirmed non-churn conflict, "resolve by hand") may demote the unit to
    `held`/`rebase_conflict` -- not any other nonzero exit."""
    step = _step_3f_bis()
    eq2_at = step.index('"$ensure_current_rc" -eq 2')
    # `--reason-code rebase_conflict`, the actual demotion call -- not the
    # earlier explanatory comment above the if-chain, which also names
    # "rebase_conflict" while describing what the fix prevents.
    conflict_at = step.index("--reason-code rebase_conflict", eq2_at)
    assert eq2_at < conflict_at, (
        "the rebase_conflict demotion must sit behind the exit-code == 2 "
        "branch specifically, not a bare success/failure check"
    )
    # No other numbered exit-code check precedes the conflict demotion --
    # it must be reachable ONLY via the -eq 2 branch, never a catch-all.
    between = step[eq2_at:conflict_at]
    assert between.count("elif") == 0 and "else" not in between


def test_ensure_current_operational_failure_strict_stops_not_held():
    """Every OTHER nonzero exit (bad ref, a merge that never started, a
    failed commit, a corrupt log, ...) is an operational failure this loop
    cannot resolve by holding the unit -- it must whole-wave STRICT-STOP,
    never fall into the `rebase_conflict` demotion meant only for a
    confirmed content conflict."""
    step = _step_3f_bis()
    eq2_at = step.index('"$ensure_current_rc" -eq 2')
    conflict_at = step.index("--reason-code rebase_conflict", eq2_at)
    else_at = step.index("else", conflict_at)
    fi_at = step.index(" fi ", else_at)
    assert eq2_at < conflict_at < else_at < fi_at, (
        "the operational-failure branch must be a genuine `elif ... else` "
        "sibling AFTER the exit-code == 2 conflict branch"
    )
    else_body = step[else_at:fi_at]
    assert "strict-stop" in else_body
    assert "--reason-code rebase_conflict" not in else_body, (
        "an operational ensure_current failure must never be recorded as "
        "rebase_conflict -- only a genuine exit-code-2 conflict may"
    )

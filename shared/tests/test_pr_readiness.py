"""What state is this pull request in? (iterate-2026-07-31-f11-delivery-truth)

Everything here fails towards NOT ready: an unrecognised merge state, a partially
registered rollup and a first-look empty rollup are all `pending`, because each of
them read as green in an earlier draft and each was a way to merge on no evidence.

Split out of ``test_pr_delivery.py`` to keep both files under the 300-line source
limit (constitution; the Group H audit fails an oversize file with no baseline entry).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.pr_readiness import (  # noqa: E402
    CLEAR_MERGE_STATES,
    failing_checks,
    readiness,
)


def _run(name="ci", conclusion="SUCCESS", status="COMPLETED"):
    return {"__typename": "CheckRun", "name": name, "conclusion": conclusion,
            "status": status, "detailsUrl": "u"}


def _ctx(context="legacy", state="SUCCESS"):
    return {"__typename": "StatusContext", "context": context, "state": state,
            "targetUrl": "u"}


def _pr(*, merge_state="CLEAN", rollup=None, state="OPEN"):
    return {"state": state, "mergeStateStatus": merge_state,
            "statusCheckRollup": rollup if rollup is not None else []}

# --- ready is not pending -----------------------------------------------------

def test_all_green_and_mergeable_is_green():
    assert readiness(_pr(rollup=[_run()]))["state"] == "green"


def test_a_running_check_is_pending():
    assert readiness(_pr(rollup=[_run(status="IN_PROGRESS", conclusion=None)]))["state"] == "pending"


def test_a_queued_legacy_context_is_pending():
    assert readiness(_pr(rollup=[_ctx(state="PENDING")]))["state"] == "pending"


def test_a_failing_check_is_failed_not_green():
    assert readiness(_pr(rollup=[_run(conclusion="FAILURE")]))["state"] == "failed"


def test_an_uncomputed_merge_state_is_pending():
    """GitHub computes mergeability asynchronously after a push; `UNKNOWN` is a
    "not yet" and must never be read as a clear one (external review)."""
    assert readiness(_pr(merge_state="UNKNOWN", rollup=[_run()]))["state"] == "pending"


def test_a_missing_merge_state_is_pending_not_green():
    assert readiness(_pr(merge_state="", rollup=[_run()]))["state"] == "pending"


def test_states_that_waiting_might_clear_are_blocked_never_green():
    """BLOCKED and DRAFT can clear without us: a thread gets resolved, a required review
    arrives, a draft is marked ready."""
    for state in ("BLOCKED", "DRAFT"):
        assert readiness(_pr(merge_state=state, rollup=[_run()]))["state"] == "blocked", state


def test_a_conflicted_branch_is_refreshable_not_merely_blocked():
    """DIRTY was bucketed with BLOCKED, so an iterate that conflicted after another one
    merged spent 1800 seconds polling a state one `ensure_current` would have cleared —
    and the resolver is already wired into this ladder (Stage 2)."""
    assert readiness(_pr(merge_state="DIRTY", rollup=[_run()]))["state"] == "refresh_needed"


def test_an_unrecognised_merge_state_is_never_read_as_clear():
    """`readiness` used to fall through to green for anything it did not recognise, so a
    new or renamed MergeStateStatus member would license a merge on no evidence — the one
    direction this module must never fail (Stage 2)."""
    for state in ("SOMETHING_NEW", "QUEUED", "MERGE_QUEUE"):
        result = readiness(_pr(merge_state=state, rollup=[_run()]))
        assert result["state"] == "pending", state
        assert state in result["reason"]


def test_behind_is_its_own_answer_so_the_driver_can_refresh():
    """Not `pending`: nothing but a refresh clears BEHIND, so waiting on it is
    waiting forever — the same shape as the bug being fixed one level up."""
    assert readiness(_pr(merge_state="BEHIND", rollup=[_run()]))["state"] == "refresh_needed"


def test_checks_do_not_vanish():
    """Right after a refresh push the new head's rollup can be EMPTY, which would
    otherwise read as "green, zero checks" and merge an untested commit. Every NAME seen
    earlier must report again before the door opens."""
    seen = ["a", "b", "c"]
    assert readiness(_pr(rollup=[]), seen_names=seen)["state"] == "pending"
    all_back = _pr(rollup=[_run("a"), _run("b"), _run("c")])
    assert readiness(all_back, seen_names=seen)["state"] == "green"


def test_the_floor_is_a_name_set_not_a_count():
    """The count-based version could be satisfied by three checks reporting where three
    were seen before — but if the base gained two workflows in the refresh, the new head
    has five and merging on three merges before two of them exist (Stage 2, HIGH)."""
    seen = ["a", "b", "c"]
    three_but_wrong_ones = _pr(rollup=[_run("a"), _run("d"), _run("e")])
    result = readiness(three_but_wrong_ones, seen_names=seen)
    assert result["state"] == "pending"
    assert "b" in result["reason"] and "c" in result["reason"]


def test_an_empty_rollup_is_not_believed_until_a_poll_has_passed():
    """Mergeability flips to CLEAN faster than Actions creates check runs, so an empty
    rollup on the FIRST look is indistinguishable from a host that runs none. Believing
    it immediately merges on the strength of checks that had not registered yet
    (Stage 2, HIGH)."""
    first_look = readiness(_pr(rollup=[]), settled=False)
    assert first_look["state"] == "pending"
    assert "registered" in first_look["reason"]
    assert readiness(_pr(rollup=[]), settled=True)["state"] == "green"


def test_a_null_rollup_entry_does_not_crash_the_verdict():
    """An AttributeError inside a classifier costs the verdict it was meant to give —
    the sibling reader `_pr_blocker_causes._reported` already guards this."""
    pr = {"state": "OPEN", "mergeStateStatus": "CLEAN",
          "statusCheckRollup": [None, "junk", _run("ci")]}
    assert readiness(pr)["state"] == "green"
    assert failing_checks(pr["statusCheckRollup"]) == []


def test_a_host_that_runs_no_checks_is_green_and_says_how_many():
    """Case C: an unprotected repo often has zero PR checks. Merging is correct
    there, but the count must be reported so "delivered" can never read as
    "the host confirmed it"."""
    result = readiness(_pr(rollup=[]))
    assert result["state"] == "green"
    assert result["checks_observed"] == 0


def test_skipped_and_neutral_do_not_block_readiness():
    """A `needs:`-skipped required job is a pass (B4.5), and the watcher already
    treats it so — readiness must agree, or the two disagree about one payload."""
    rollup = [_run("a", conclusion="SKIPPED"), _run("b", conclusion="NEUTRAL"), _run("c")]
    assert readiness(_pr(rollup=rollup))["state"] == "green"


def test_readiness_reports_the_count_it_observed():
    assert readiness(_pr(rollup=[_run("a"), _ctx("b")]))["checks_observed"] == 2


# --- the promoted helper ------------------------------------------------------

def test_failing_checks_is_the_one_implementation():
    """It MOVED here from `watch_pr_delivery`; the watcher imports it. Two views
    of one payload is exactly the drift PR #503 was about."""
    rollup = [_run("bad", conclusion="FAILURE"), _ctx("worse", state="ERROR"), _run("ok")]
    names = {f["name"] for f in failing_checks(rollup)}
    assert names == {"bad", "worse"}


def test_failing_checks_tolerates_a_missing_rollup():
    assert failing_checks(None) == []


# --- the merge-state vocabulary must not drift from the blocker probe's ---------
#
# `lib/_pr_blocker_causes` already closed this enum for the blocker probe, and Stage 2
# review flagged `pr_readiness` re-deriving it as a second view of one vocabulary. The
# two answer different questions, so they are not merged — but they must never
# CONTRADICT each other, and that is mechanical rather than a matter of judgement.

def test_readiness_never_calls_clear_a_state_the_blocker_probe_calls_blocking():
    from lib._pr_blocker_causes import merge_state_blocks

    for state in sorted(CLEAR_MERGE_STATES):
        assert not merge_state_blocks(state), (
            f"readiness treats {state} as clear to merge while the blocker probe reports "
            "it as blocking — one of the two is wrong"
        )


def test_every_state_the_blocker_probe_calls_blocking_keeps_readiness_off_green():
    from lib._pr_blocker_causes import merge_state_blocks

    for state in ("BLOCKED", "DIRTY", "DRAFT"):
        if not merge_state_blocks(state):
            continue
        result = readiness(_pr(merge_state=state, rollup=[_run()]))
        assert result["state"] != "green", f"{state} reached green: {result}"

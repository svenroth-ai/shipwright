"""Prose guards for campaign-dag-scheduler R5b ("serial merge lane: review
pinning, staleness cascade, STRICT-STOP") — the drain sweep (AC5), step-3h
status mapping (AC6), and second-round external-review-fix acceptance
criteria. Split out of `test_campaign_r5b_merge_lane_prose.py` when it
crossed the 300-line guideline (round 2) — AC1-AC4 (3f-bis/3g core) stay
there; this file covers AC5 onward, reusing the same harness. Step 4's own
held-merge reconciliation pass (round 3-4) split further, into the sibling
`test_campaign_r5b_merge_lane_prose_finalize.py`, when this file itself
crossed the guideline (round 5)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _campaign_prose_harness import (  # noqa: E402
    CAMPAIGN_DOC,
    step_3f_bis as _step_3f_bis,
    step_3g as _step_3g,
)


def _step_3h() -> str:
    """Mirrors `_campaign_prose_harness.step_3g` — from `3h.` to `3i.`."""
    import re

    text = CAMPAIGN_DOC.read_text(encoding="utf-8")
    start = re.search(r"(?m)^\s*3h\.", text)
    assert start, "campaign-mode.md must define loop step `3h.`"
    body = text[start.start():]
    end = re.search(r"(?m)^\s*3i\.", body)
    from _campaign_prose_harness import norm
    return norm(body[:end.start()] if end else body)


def _step_4() -> str:
    import re

    text = CAMPAIGN_DOC.read_text(encoding="utf-8")
    start = re.search(r"(?m)^4\. \*\*Finalize:\*\*", text)
    assert start, "campaign-mode.md must define step 4 (Finalize)"
    body = text[start.start():]
    end = re.search(r"(?m)^5\. \*\*Release prompt", body)
    from _campaign_prose_harness import norm
    return norm(body[:end.start()] if end else body)


# --- AC5: STRICT-STOP sweep + max_drain_seconds + guaranteed lock release ---


def test_strict_stop_is_redefined_to_drain_before_finalize():
    norm = CAMPAIGN_DOC.read_text(encoding="utf-8").lower()
    assert "campaign_drain.py" in norm
    assert "swept_never_started" in norm
    assert "swept_after_build" in norm
    assert "lease_expired_during_drain" in norm
    assert "drain_timeout" in norm


def test_step_4_drains_before_finalize_and_releases_after():
    step = _step_4()
    drain_at = step.index("campaign_drain.py")
    finalize_at = step.index("finalize --state")
    release_at = step.index("check_campaign_session_lock.py\" release")
    assert drain_at < finalize_at < release_at, (
        "step 4 must run drain, then finalize, then release the session lock "
        "-- in that order"
    )


def test_exit_4_sweeps_and_finalizes_instead_of_stopping_without_finalize():
    section = CAMPAIGN_DOC.read_text(encoding="utf-8")
    at = section.find("exit 4 →")
    assert at >= 0, "step 3a must document exit 4"
    window = section[at:at + 700].lower()
    assert "swept_never_started" in window
    assert "finalize" in window


# --- AC6: step 3h status-vocabulary mapping ---


def test_step_3h_maps_merged_to_complete_failed_to_failed():
    step = _step_3h()
    assert "merged" in step and "complete" in step
    assert "failed" in step


def test_step_3h_maps_swept_reason_codes_to_pending_not_failed():
    step = _step_3h()
    assert "swept_never_started" in step
    assert "swept_after_build" in step
    assert "pending" in step


def test_step_3h_does_not_change_campaign_progress_enum():
    step = _step_3h()
    assert "no new token added" in step or "unchanged by this" in step


# --- Second-round external review fixes (glm + openai, both HIGH/MEDIUM) ---


def test_pr_identity_is_verified_before_merge_not_only_head_sha():
    """External review (code-reviewer + doubt-reviewer, high): `--match-head-
    commit` alone proves only the head SHA, never that this is still the
    pinned PR OBJECT (node id / head ref / base ref). Round 5 (Tier-3
    review, medium): field-name presence alone does not prove each fresh
    value is actually COMPARED against its pinned counterpart, or that a
    mismatch fail-closes — assert the three real equality checks and their
    STRICT-STOP guards directly, not just that the names appear somewhere
    in the window."""
    step = _step_3g()
    identity_at = step.index("pr_identity=")
    merge_at = step.rindex('gh pr merge')
    assert identity_at < merge_at, "PR-identity check must run before the merge call"
    window = step[identity_at:merge_at]
    assert "pinned_pr_node_id" in window
    assert "pinned_pr_head_ref" in window
    assert "pinned_pr_base_ref" in window

    def _fail_closed_equality_check(field: str, pinned_var: str) -> None:
        check = f'{field} <<<"$pr_identity")" = "${pinned_var}" ] || strict-stop'
        assert check in window, (
            f"{pinned_var} must be compared against a FRESH {field} read and "
            "fail-closed (|| STRICT-STOP) on any mismatch, not merely be "
            "read into a variable somewhere in this window"
        )

    _fail_closed_equality_check(".id", "pinned_pr_node_id")
    _fail_closed_equality_check(".headrefname", "pinned_pr_head_ref")
    _fail_closed_equality_check(".baserefname", "pinned_pr_base_ref")


def test_rebase_cascade_actually_invokes_ensure_current_not_just_a_comment():
    """External review (glm + openai, high): the first draft only NAMED
    `ensure_current.py` in a comment; a CONFLICTING branch never actually
    got rebased. This asserts a real, checked invocation exists — checked
    via `if ...; then ... else ...` (R5b round 2 replaced the earlier
    `|| { ...; }` compound-command shape; see the next test for why)."""
    step = _step_3f_bis()
    cascade_at = step.index("max_rebase_reviews")
    ensure_at = step.index('uv run "{shared_root}/scripts/tools/ensure_current.py"', cascade_at)
    window = step[ensure_at:ensure_at + 400]
    assert "); then" in window, "the ensure_current.py call must be CHECKED, not fire-and-forget"
    fail_window = step[ensure_at:ensure_at + 1200]
    assert "else" in fail_window and "held" in fail_window, (
        "the ensure_current.py failure path must be a distinct `else` branch "
        "that demotes the unit to held"
    )


def test_ensure_current_failure_does_not_fall_through_to_the_success_only_steps():
    """Tier-3 review, R5b round 2, data-loss finding: an earlier draft used
    `guard=$(...) || { ...held... }` — bash's `||` compound-command `{ }`
    block only guards WHAT RUNS on failure; everything textually AFTER it
    (the counter bump, the re-entry instruction) ran unconditionally on
    EITHER path, including right after marking the unit `held` — silently
    re-entering 3f-bis for a unit the same block had just demoted out of
    this wave. The fix branches the success-only steps inside the `if`'s
    own body, never reachable from the `else`."""
    step = _step_3f_bis()
    cascade_at = step.index("max_rebase_reviews")
    ensure_at = step.index('uv run "{shared_root}/scripts/tools/ensure_current.py"', cascade_at)
    then_at = step.index("; then", ensure_at)
    else_at = step.index("else", then_at)
    fi_at = step.index("fi", else_at)
    success_body = step[then_at:else_at]
    failure_body = step[else_at:fi_at]
    assert "rebase_count + 1" in success_body, (
        "the counter bump must sit inside the success (`then`) branch"
    )
    assert "re-enter 3f-bis" in success_body
    assert "rebase_count + 1" not in failure_body, (
        "the failure (`else`) branch must never reach the counter-bump / "
        "re-entry steps meant only for a successful rebase"
    )
    assert "held" in failure_body


def test_unknown_mergeable_is_polled_bounded_before_treated_as_current():
    """External review (glm + openai, medium): `UNKNOWN` right after a push
    can resolve to `CONFLICTING` moments later; promoting on it immediately
    can skip the currency check it exists to run."""
    step = _step_3f_bis()
    mergeable_at = step.index('mergeable="unknown"')
    poll_window = step[mergeable_at:mergeable_at + 400]
    assert "for i in" in poll_window
    assert "unknown" in poll_window


def test_commit_parent_is_asserted_after_the_reviews_json_commit():
    """External review (code-reviewer + doubt-reviewer, medium): the
    pre-commit HEAD==reviewed_head assert alone leaves a window between
    `git add` and `git commit` unchecked."""
    step = _step_3f_bis()
    commit_at = step.index('commit -m "chore(review): record the delegated cascade')
    push_at = step.index('git -c "$unit_wt" push')
    window = step[commit_at:push_at]
    assert "rev-parse head^" in window
    assert "pinned_reviewed_head" in window


def test_rebase_count_resets_on_a_fresh_attempt():
    """External review (glm, medium): `$run_dir` is per-unit, not per-
    attempt — a resumed `held -> pending` unit must not inherit a prior
    attempt's rebase-cascade count."""
    # 3b's own reset lives just before the 3f-bis prose region this harness
    # extracts, so read the whole doc for this one rather than the sliced
    # step body.
    full = CAMPAIGN_DOC.read_text(encoding="utf-8").lower()
    reset_at = full.index("reset `rebase_count` for a fresh attempt")
    window = full[reset_at:reset_at + 700]
    assert 'rm -f "$run_dir/rebase_count"' in window


def test_step_4_drain_and_finalize_are_checked_not_bare():
    """External review (code-reviewer + doubt-reviewer, medium): the first
    draft's step-4 code fence had three bare lines, unlike every other
    command in this doc. `norm()` strips backticks, so bound the window by
    the drain/release calls themselves rather than a fence delimiter."""
    step = _step_4()
    drain_at = step.index("campaign_drain.py")
    release_at = step.index('check_campaign_session_lock.py" release')
    window = step[drain_at:release_at]
    assert window.count("|| strict-stop") >= 2, (
        "both the drain and finalize lines in step 4's code fence must be "
        "STRICT-STOP-chained"
    )


def test_step_4_release_line_is_also_checked_not_bare():
    """Tier-3 review, R5b round 11, blocking: the prose right after this
    code fence already CLAIMED "both commands above are `|| STRICT-STOP`-
    chained", but the release command itself had no chaining at all, so a
    failed release fell through silently instead of reporting anything --
    the round-9/round-10 fall-through class, on the one line the sibling
    test above deliberately excludes from its own window."""
    step = _step_4()
    release_at = step.index('check_campaign_session_lock.py" release')
    window = step[release_at:release_at + 300]
    assert "|| strict-stop" in window, (
        "the session-lock release line must be STRICT-STOP-chained too, "
        "not just the drain and finalize lines before it"
    )


def test_drain_timeout_worker_continuation_limitation_is_disclosed():
    """Tier-3 review, R5b round 2, correctness finding: a `drain_timeout`
    force-transition changes the RECORD, not the WORKER — a `merging` unit's
    own in-flight `gh pr merge` can complete after its row is force-held,
    since this framework has no way to cancel an already-spawned `Task`.
    Neither of the reviewer's suggested remedies (cancel/fence the worker;
    never finalize until confirmed stopped) is implementable with today's
    tooling, so this is accepted as a documented, scoped-down limitation
    (mirrors the ADR's own disposition of the adjacent lock-release
    pushback) rather than a code change — this test guards that the
    disclosure itself cannot be silently dropped."""
    full = CAMPAIGN_DOC.read_text(encoding="utf-8").lower()
    assert "known, accepted limitation" in full
    assert "cancel an already-spawned" in full

"""Prose guards for campaign-dag-scheduler R5b ("serial merge lane: review
pinning, staleness cascade, STRICT-STOP") — the parts of its own Acceptance
Criteria that are best proved against the doc's actual text rather than
executable code, mirroring `test_campaign_step_3f_bis.py`'s own style and
reusing its harness.

Covers AC1-AC4 (3f-bis/3g core: HEAD==reviewed_head, the rebase cascade, the
merge-confirmation bound). AC5 onward (drain/finalize, step-3h status mapping,
and the second-round external-review fixes) live in the sibling
`test_campaign_r5b_merge_lane_prose_drain.py`, split out when this file
crossed the 300-line guideline (round 2).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _campaign_prose_harness import (  # noqa: E402
    step_3f_bis as _step_3f_bis,
    step_3g as _step_3g,
)


# --- AC1: HEAD == reviewed_head exactness, before the reviews.json commit ---


def test_head_equals_reviewed_head_is_asserted_before_the_commit():
    step = _step_3f_bis()
    assert "current_head" in step and "pinned_reviewed_head" in step
    assert_at = step.index('"$current_head" != "$pinned_reviewed_head"')
    commit_at = step.index('commit -m "chore(review): record the delegated cascade')
    assert assert_at < commit_at, (
        "the HEAD == reviewed_head assertion must precede the reviews.json commit"
    )


def test_a_head_deviation_invalidates_the_pin_and_demotes_reenters():
    step = _step_3f_bis()
    tail = step[step.index('"$current_head" != "$pinned_reviewed_head"'):]
    window = tail[:1400]
    assert "--mode invalidate" in window
    assert "--status built" in window
    assert "re-enter 3f-bis" in window


def test_head_deviation_uses_a_real_if_else_not_a_fallthrough_comment():
    """Tier-3 external review, R5b round 9, blocking: `cond || { ...; #
    comment }` has no bash meaning past its own closing brace, so a literal
    shell (or an agent following these steps mechanically) fell straight
    through to the unconditional commit/push below regardless of whether the
    assertion failed. The fix must be a genuine `if`/`else` branch, not a
    stronger-worded comment -- assert the control-flow keywords themselves,
    and that the commit only lives inside the `else`."""
    step = _step_3f_bis()
    if_at = step.index('if [ "$current_head" != "$pinned_reviewed_head" ]; then')
    else_at = step.index("else", if_at)
    commit_at = step.index('commit -m "chore(review): record the delegated cascade')
    assert if_at < else_at < commit_at, (
        "the HEAD-mismatch branch must be a real `if ... else` whose `else` "
        "precedes the reviews.json commit, not a `||` fallthrough"
    )
    then_body = step[if_at:else_at]
    assert "git add" not in then_body and "commit -m" not in then_body, (
        "the commit sequence must not appear inside the HEAD-mismatch `if` "
        "branch itself -- it belongs only in the `else`"
    )


def test_commit_parent_mismatch_also_uses_a_real_if_else_not_a_fallthrough():
    """The second half of round 9's finding: the commit-parent fencing check
    had the identical `cond || { ...; # skip push and below }` shape, with
    push and the shipped_head write left as unconditional commands after it.
    Must now nest as a real `if`/`else` too, with push only inside the
    `else`."""
    step = _step_3f_bis()
    if_at = step.index('if [ "$(git -c "$unit_wt" rev-parse head^)" != "$pinned_reviewed_head" ]; then')
    else_at = step.index("else", if_at)
    push_at = step.index('git -c "$unit_wt" push')
    assert if_at < else_at < push_at, (
        "the commit-parent-mismatch branch must be a real `if ... else` "
        "whose `else` precedes the push, not a `||` fallthrough"
    )
    then_body = step[if_at:else_at]
    assert "push" not in then_body, (
        "push must not appear inside the commit-parent-mismatch `if` branch "
        "itself -- it belongs only in the `else`"
    )
    assert "reset --hard head^" in then_body


def test_invalidated_pin_cannot_reach_reviewed_or_merging_without_a_fresh_cascade():
    """Round 10 (Tier-3 external review, blocking): round 9's fix correctly
    stopped the invalidate branches from reaching commit/push, but a demoted
    unit still fell through into the UNCONDITIONAL `built -> reviewed`
    promotion and currency check further down the same step -- reaching
    `merging` without a fresh review cascade ever running. `pin_still_valid`
    must be declared before either mismatch check, cleared by both, and gate
    the promotion as a real `if`, not by the "re-enter 3f-bis" prose alone."""
    step = _step_3f_bis()
    declared_at = step.index("pin_still_valid=true")
    head_if_at = step.index('if [ "$current_head" != "$pinned_reviewed_head" ]; then')
    assert declared_at < head_if_at, (
        "pin_still_valid must be initialised before the HEAD-mismatch check "
        "can possibly clear it"
    )
    assert step.count("pin_still_valid=false") == 2, (
        "both the HEAD-mismatch and commit-parent-mismatch branches must "
        "clear pin_still_valid"
    )
    promote_guard_at = step.index('if [ "$pin_still_valid" = "true" ]; then')
    promote_at = step.index("--status reviewed")
    assert promote_guard_at < promote_at, (
        "the built -> reviewed promotion must sit inside the pin_still_valid "
        "guard, not run unconditionally after either invalidate branch"
    )
    guarded_body = step[promote_guard_at:]
    merging_at = guarded_body.index("--status merging")
    assert merging_at > 0, "the merging transition must also be inside the guard"


# --- AC2/AC3: currency check in `reviewed`, rebase cascade, max_rebase_reviews ---


def test_built_promotes_to_reviewed_before_the_currency_check():
    step = _step_3f_bis()
    promote_at = step.index("--status reviewed")
    mergeable_at = step.index("--json mergeable")
    assert promote_at < mergeable_at, (
        "built -> reviewed must be recorded before the currency check runs"
    )


def test_currency_check_promotes_reviewed_to_merging_only_when_current():
    step = _step_3f_bis()
    assert "mergeable" in step
    assert "--status merging" in step


def test_conflicting_mergeable_triggers_the_rebase_cascade():
    step = _step_3f_bis()
    assert "conflicting" in step
    assert "max_rebase_reviews" in step
    assert "rebase_count" in step


def test_max_rebase_reviews_is_two_and_exhaustion_demotes_to_held():
    """Round 7 (Tier-3 review): the counter parse + the `>= 2` exhaustion
    boundary itself moved into `lib.rebase_cascade` (real, executable tests:
    `test_rebase_cascade.py::TestDecideRebaseAction`) — this doc now only
    calls that script and branches on its answer."""
    step = _step_3f_bis()
    assert "max_rebase_reviews = 2" in step
    decide_at = step.index("rebase_cascade.py\" decide --rebase-count")
    window = step[decide_at:decide_at + 500]
    assert '"$rebase_action" = "exhausted"' in window
    assert "--status held" in window
    assert "staleness_cascade_exhausted" in window


def test_rebase_counter_is_extracted_not_reinlined():
    """Round 7 (Tier-3 review): guards against a future edit silently
    reintroducing the inline `cat`/`case`/`-ge` counter logic this round
    replaced with real, tested Python."""
    step = _step_3f_bis()
    assert "rebase_cascade.py" in step
    assert 'case "$rebase_count" in' not in step, (
        "the rebase_count parse must stay extracted into lib.rebase_cascade, "
        "not re-inlined as a bash `case` guard"
    )


def test_staleness_trigger_is_scoped_to_this_units_own_branch():
    """The negative half of the staleness-cascade requirement: an unrelated
    sibling's merge advancing origin/<default> must never be conflated with
    THIS unit's own branch needing a rebase."""
    step = _step_3f_bis()
    assert "unrelated sibling" in step
    assert '"mergeable == "mergeable"' in step or "mergeable ==" in step


# --- AC4: merge-confirmation bound, strict SHA, cmd_mark_merged, no rev-parse fallback ---


def test_merge_commit_confirmation_is_bounded_and_checked_after_the_merged_poll():
    step = _step_3g()
    merged_poll_done_at = step.rindex('"merged" ] || strict-stop')
    confirm_at = step.index("mergecommit -q")
    assert confirm_at > merged_poll_done_at, (
        "mergeCommit.oid must be read only AFTER the existing MERGED poll, "
        "never before (it lags the merge exactly like PR state does)"
    )
    assert "deadline" in step, "the mergeCommit confirmation wait must be bounded"


def test_merge_confirmation_timeout_demotes_the_unit_not_the_whole_wave():
    step = _step_3g()
    assert "merge_confirmation_timeout" in step
    timeout_at = step.index("merge_confirmation_timeout")
    window = step[max(0, timeout_at - 400):timeout_at + 100]
    assert "--status held" in window
    assert "--force" in window and "--confirm-no-task-running" in window


def test_confirmed_sha_is_recorded_via_mark_merged_not_record_or_mark():
    step = _step_3g()
    invocation = 'loop_claim.py" mark-merged'
    assert invocation in step
    mark_merged_at = step.index(invocation)
    window = step[mark_merged_at:mark_merged_at + 400]
    assert "--merged-commit" in window
    assert "--attempt-id" in window


def test_no_git_rev_parse_origin_default_fallback_for_merged_commit():
    step = _step_3g()
    assert "rev-parse origin" not in step, (
        "3g must never fall back to `git rev-parse origin/{default}` for the "
        "merged commit — a concurrent sibling merge can make that an "
        "ancestrally-true but semantically-wrong SHA"
    )


def test_head_pin_reads_shipped_head_from_review_pin_json_directly():
    step = _step_3g()
    assert ".pin.shipped_head" in step
    head_pin_at = step.index('head_pin="--match-head-commit $head_sha"')
    read_at = step.index(".pin.shipped_head")
    assert read_at < head_pin_at, (
        "head_pin's SHA must be read from review_pin.json's own "
        "shipped_head field before head_pin is constructed from it"
    )


def test_merge_commit_confirmation_distinguishes_gh_query_failure_from_not_yet_merged():
    """External review, R5b round 3, medium: a persistent `gh` command
    failure (network, auth, rate limit) was indistinguishable from "the
    query succeeded and mergeCommit is merely not populated yet" — both
    silently rode out the full 300s bound and landed on
    `merge_confirmation_timeout`, which asserts the PR genuinely IS merged
    and only the SHA is late. Three consecutive `gh` failures (not the
    first, since this loop already tolerates one transient blip by
    retrying every 5s) must STRICT-STOP instead of silently exhausting the
    timeout and mislabeling a broken query as a merged-but-unconfirmed PR."""
    step = _step_3g()
    assert "gh_query_failures" in step
    fail_at = step.index("gh_query_failures")
    window = step[fail_at:fail_at + 1400]
    assert "gh_query_failures + 1" in window
    assert '"$gh_query_failures" -lt 3' in window
    assert "strict-stop" in window

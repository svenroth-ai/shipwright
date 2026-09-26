"""Prose guards for campaign-dag-scheduler R5b's second-round external-review
fixes (glm + openai, both HIGH/MEDIUM) plus the drain-timeout worker-
continuation disclosure. Split out of `test_campaign_r5b_merge_lane_prose_
drain.py` when it crossed the 300-line guideline (round 19) — that file keeps
AC5/AC6; this file covers only the second-round fixes, reusing the same
harness. `_step_4` is duplicated rather than imported, matching this suite's
own convention (e.g. `test_campaign_r5b_merge_lane_prose_finalize.py`'s own
duplicated helper) since sharing it would need a new module neither sibling
otherwise requires.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _campaign_prose_harness import (  # noqa: E402
    CAMPAIGN_DOC,
    norm,
    step_3f_bis as _step_3f_bis,
    step_3g as _step_3g,
)


def _step_4() -> str:
    import re

    text = CAMPAIGN_DOC.read_text(encoding="utf-8")
    start = re.search(r"(?m)^4\. \*\*Finalize:\*\*", text)
    assert start, "campaign-mode.md must define step 4 (Finalize)"
    body = text[start.start():]
    end = re.search(r"(?m)^5\. \*\*Release prompt", body)
    return norm(body[:end.start()] if end else body)


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
    via its own captured exit code (`ensure_current_rc=$?`, R5b round 17,
    which replaced the bare `if ...; then ... else ...` this test used to
    assert — R5b round 2 had itself replaced an even earlier `|| { ...; }`
    compound-command shape; see the next test for why capturing matters)."""
    step = _step_3f_bis()
    cascade_at = step.index("max_rebase_reviews")
    ensure_at = step.index('uv run "{shared_root}/scripts/tools/ensure_current.py"', cascade_at)
    window = step[ensure_at:ensure_at + 400]
    assert "ensure_current_rc=$?" in window, "the ensure_current.py call must be CHECKED, not fire-and-forget"
    fail_window = step[ensure_at:ensure_at + 2400]
    assert "-eq 2" in fail_window and "held" in fail_window, (
        "the ensure_current.py exit-code-2 (confirmed conflict) path must be "
        "a distinct branch that demotes the unit to held"
    )


def test_ensure_current_failure_does_not_fall_through_to_the_success_only_steps():
    """Tier-3 review, R5b round 2, data-loss finding: an earlier draft used
    `guard=$(...) || { ...held... }` — bash's `||` compound-command `{ }`
    block only guards WHAT RUNS on failure; everything textually AFTER it
    (the counter bump, the re-entry instruction) ran unconditionally on
    EITHER path, including right after marking the unit `held` — silently
    re-entering 3f-bis for a unit the same block had just demoted out of
    this wave. The fix branches the success-only steps inside the `if`'s
    own body, never reachable from the `elif`/`else` (round 17: a THIRD,
    operational-failure branch was added alongside the exit-code-2 `elif`;
    the success-only steps must stay unreachable from either)."""
    step = _step_3f_bis()
    cascade_at = step.index("max_rebase_reviews")
    ensure_at = step.index('uv run "{shared_root}/scripts/tools/ensure_current.py"', cascade_at)
    then_at = step.index("; then", ensure_at)
    elif_at = step.index("elif", then_at)
    else_at = step.index("else", elif_at)
    fi_at = step.index(" fi ", else_at)
    success_body = step[then_at:elif_at]
    conflict_body = step[elif_at:else_at]
    operational_body = step[else_at:fi_at]
    assert "rebase_count + 1" in success_body, (
        "the counter bump must sit inside the success (`then`) branch"
    )
    assert "re-enter 3f-bis" in success_body
    for failure_body in (conflict_body, operational_body):
        assert "rebase_count + 1" not in failure_body, (
            "no failure branch may reach the counter-bump / re-entry steps "
            "meant only for a successful rebase"
        )
    assert "held" in conflict_body
    assert "held" not in operational_body, (
        "the operational-failure branch must STRICT-STOP, never demote to held"
    )


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

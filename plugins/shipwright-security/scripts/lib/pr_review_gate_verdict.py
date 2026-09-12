"""Compose stage 2's final `PR Review` commit-status verdict — the single seam
where every upstream signal (prep-stage success, the trusted tier decision,
the generated-only classifier, the waiver, and the review outcome) becomes one
posted state.

Kept as one small pure function, separate from `review_record_tier.decide`
(decides only whether a review is *required*) and
`review_record_tier.classify_generated_only` (decides only whether the diff is
regenerated *content*), because this seam is where a regression could quietly
turn a real review failure into a green status — the exact class of bug
FR-01.17 (E)7 exists to rule out. One function, one set of tests, is how the
composition itself stays reviewable and pinned instead of drifting inside
workflow YAML nobody diffs for logic changes.

See .shipwright/planning/iterate/iterate-2026-09-10-pr-review-generated-only.md.
"""

from __future__ import annotations

__all__ = ["decide_gate"]

# A GitHub Actions step's `outcome` when its own `if:` evaluated false, or when
# it never ran at all (empty string here — this workflow's own steps always
# populate an env var from `steps.<id>.outcome`, which GitHub renders as "" for
# a step that was never reached).
_NOT_RUN_OUTCOMES = frozenset({"", "skipped"})


def decide_gate(
    *,
    stage1_ok: bool,
    tier_ok: bool,
    all_generated: bool,
    all_generated_reason: str,
    needs_review: bool,
    waiver_consumed_ok: bool,
    review_outcome: str,
    tier_reason: str,
) -> tuple[str, str]:
    """Return ``(state, description)`` for the ``PR Review`` commit status.

    ``review_outcome`` is the raw GitHub Actions step outcome for the
    "Run Tier-3 PR review" step: ``"success"``, ``"failure"``,
    ``"cancelled"``, ``"skipped"``, or ``""`` when it never ran.

    The `all_generated` branch is deliberately narrow: it only short-circuits
    to `success` when the review step did not actually run — which is what it
    structurally is whenever `all_generated` gated that step off in the
    workflow. If the review step ran anyway and failed (a wiring bug, a race,
    a future edit that loosens the gating `if:`), that failure must win — a
    positively-identified "nothing to review" case must never mask a real
    review failure. This is the guard hard constraint 4 asks for.

    It must also never mask a WAIVER failure. `all_generated=True` and
    `needs_review=False` could once both hold for a PR whose only changed
    path was a corroborated `reviews.json` (`is_generated_path` AND, at the
    time, `is_safe_to_skip_review`); Round 4 of
    iterate-2026-09-11-pr-review-evidence-filter-gap removed `reviews.json`'s
    `is_safe_to_skip_review` grant, so `needs_review=False` now structurally
    requires `reviews.json` among the changed paths (`review_record_tier
    .decide`'s waiver-corroboration check) while that same path always makes
    `classify_generated_only` return `False` — making this combination
    currently unreachable through the real workflow. The check below stays
    as defense-in-depth against a future loosening of either function, not
    because the combination is reachable today: the "Consume the one-shot
    review waiver" step still runs whenever `needs_review=False` (gated on
    that, not on `all_generated`) and can fail (a transient API error), so if
    the combination ever becomes reachable again that failure must win — the
    waiver-failure check is ordered BEFORE the `all_generated` short-circuit
    (Stage-2 code review, PR-shaped: all-generated + waived +
    waiver-consumption failure).

    When a PR is BOTH all-generated and waived AND the waiver consumed
    cleanly, the `all_generated` branch still runs first and posts
    `all_generated_reason` — not `tier_reason`. Deliberate: a self-explaining
    "nothing to review" is more accurate than a waiver-corroboration message
    when both are true (external code-review finding; pinned by
    `test_all_generated_and_waived_pr_posts_the_generated_reason_not_the_tier_reason`).
    """
    if not stage1_ok:
        return "failure", "preparation stage failed — nothing was reviewed"
    if not tier_ok:
        return "failure", "could not determine whether a review was required"
    if not needs_review and not waiver_consumed_ok:
        return "failure", "review waiver consumption failed — review required"
    if all_generated and review_outcome in _NOT_RUN_OUTCOMES:
        return "success", all_generated_reason
    if review_outcome == "success":
        return "success", "reviewed — no blocking findings"
    if not needs_review and waiver_consumed_ok:
        return "success", tier_reason
    return "failure", "review blocked or did not complete"

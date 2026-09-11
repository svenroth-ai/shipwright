"""Behavioral coverage for `pr_review_gate_verdict.decide_gate` — the seam that
composes stage 2's final `PR Review` commit-status verdict from every upstream
signal. See iterate-2026-09-10-pr-review-generated-only.
"""

import sys
from pathlib import Path

PLUGIN_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))

from pr_review_gate_verdict import decide_gate  # noqa: E402


def _base(**overrides):
    args = dict(
        stage1_ok=True,
        tier_ok=True,
        all_generated=False,
        all_generated_reason="",
        needs_review=True,
        waiver_consumed_ok=False,
        review_outcome="success",
        tier_reason="",
    )
    args.update(overrides)
    return args


def test_all_generated_pr_posts_success_with_the_naming_description():
    """Acceptance 1: an all-generated changed-path list -> success, self-explaining."""
    state, desc = decide_gate(**_base(
        all_generated=True,
        all_generated_reason="no reviewable content - all 7 paths are generated artifacts",
        review_outcome="skipped",
    ))
    assert state == "success"
    assert desc == "no reviewable content - all 7 paths are generated artifacts"


def test_all_generated_but_review_step_never_reached_also_posts_success():
    """The review step is empty-string outcome, not 'skipped', before it runs."""
    state, desc = decide_gate(**_base(
        all_generated=True,
        all_generated_reason="no reviewable content - all 1 paths are generated artifacts",
        review_outcome="",
    ))
    assert state == "success"


def test_all_generated_waived_pr_with_a_failed_waiver_consumption_still_fails():
    """Stage-2 code review finding: `all_generated=True` and
    `needs_review=False` could once both hold for a PR whose only changed
    path was a corroborated `reviews.json`. Round 4 of
    iterate-2026-09-11-pr-review-evidence-filter-gap removed that path's
    `is_safe_to_skip_review` grant, making the combination currently
    unreachable through the real workflow — this pins it anyway as
    defense-in-depth: if the waiver-consumption step ever fails (a transient
    API error) while it somehow holds, that failure must win over the
    all_generated carve-out — never a masked green status.
    """
    state, desc = decide_gate(**_base(
        all_generated=True,
        all_generated_reason="no reviewable content - all 1 paths are generated artifacts",
        needs_review=False,
        waiver_consumed_ok=False,
        review_outcome="skipped",
    ))
    assert state == "failure"
    assert desc == "review waiver consumption failed — review required"


def test_a_sensitive_path_in_the_mix_means_all_generated_is_false_upstream():
    """Acceptance 2: the classifier (tested in test_review_record_tier.py) is what
    keeps a sensitive path out of this carve-out; here we confirm the composer
    still fails closed once `all_generated=False` reaches it and no review ran."""
    state, desc = decide_gate(**_base(
        all_generated=False,
        needs_review=True,
        waiver_consumed_ok=False,
        review_outcome="",
    ))
    assert state == "failure"
    assert desc == "review blocked or did not complete"


def test_model_api_failure_on_an_all_generated_pr_still_fails():
    """Acceptance 3: `all_generated=True` must never override an actual review
    failure — narrow carve-out, not a catch-all. This combination cannot occur
    through the workflow's own wiring (the review step's `if:` skips whenever
    `all_generated` is true), but the composer defends against it anyway: a
    future edit that loosens that `if:` must not silently turn a real review
    failure (crash, missing secret, empty model response) into a green status.

    GitHub Actions step outcomes are exactly `success`/`failure`/`cancelled`/
    `skipped` (there is no `timed_out` — a step timeout surfaces as
    `cancelled`); the third value below is a defensive placeholder standing
    for "anything else decide_gate has never seen", not a claim about a real
    GitHub value (Stage-3 doubt review, low finding).
    """
    for outcome in ("failure", "cancelled", "some_unrecognised_future_value"):
        state, desc = decide_gate(**_base(
            all_generated=True,
            all_generated_reason="no reviewable content - all 1 paths are generated artifacts",
            needs_review=True,
            review_outcome=outcome,
        ))
        assert state == "failure", outcome
        assert desc == "review blocked or did not complete"


def test_all_generated_and_waived_pr_posts_the_generated_reason_not_the_tier_reason():
    """External code-review finding: when a PR is BOTH all-generated and
    waived (`needs_review=False`, waiver consumed OK), the all_generated
    branch wins and posts `all_generated_reason` — not the waiver's
    `tier_reason`. Intended (a self-explaining "nothing to review" beats a
    waiver-corroboration message when both are true), but was untested and
    unstated; pinned here so a future reorder is a deliberate decision."""
    state, desc = decide_gate(**_base(
        all_generated=True,
        all_generated_reason="no reviewable content - all 1 paths are generated artifacts",
        needs_review=False,
        waiver_consumed_ok=True,
        review_outcome="skipped",
        tier_reason="trusted waiver corroborated by completed internal reviews",
    ))
    assert state == "success"
    assert desc == "no reviewable content - all 1 paths are generated artifacts"


def test_stage1_failure_fails_regardless_of_all_generated():
    state, desc = decide_gate(**_base(stage1_ok=False, all_generated=True,
                                       all_generated_reason="x", review_outcome=""))
    assert state == "failure"
    assert desc == "preparation stage failed — nothing was reviewed"


def test_tier_failure_fails_regardless_of_all_generated():
    state, desc = decide_gate(**_base(tier_ok=False, all_generated=True,
                                       all_generated_reason="x", review_outcome=""))
    assert state == "failure"
    assert desc == "could not determine whether a review was required"


def test_ordinary_reviewed_pr_still_posts_the_original_descriptions():
    state, desc = decide_gate(**_base(review_outcome="success"))
    assert (state, desc) == ("success", "reviewed — no blocking findings")

    state, desc = decide_gate(**_base(
        needs_review=False, waiver_consumed_ok=False, review_outcome="skipped",
    ))
    assert state == "failure"
    assert desc == "review waiver consumption failed — review required"

    state, desc = decide_gate(**_base(
        needs_review=False, waiver_consumed_ok=True, review_outcome="skipped",
        tier_reason="trusted waiver corroborated by completed internal reviews",
    ))
    assert (state, desc) == ("success", "trusted waiver corroborated by completed internal reviews")

"""`strip_prior_review_sections`'s fence-masking correctness (external code review).

Split out of `test_architecture_review_anchoring_defense.py` (Stop-hook bloat
gate: that file crossed its 300-line cap) — these are pure unit tests of
`strip_prior_review_sections` / `_mask_fenced_blocks` themselves, with no
CLI/mode dispatch involved, so they have no dependency on the sibling file's
`_run_main_capturing_strip_calls` helper.

A single-pattern fence masker was wrong in this module across several
external-code-review rounds, each time in a different direction: missing
CommonMark's longer-closer rule, then over-correcting to close early on a
nested shorter marker, then never masking an unclosed fence at all, then
missing 3-space indentation, then (once masking was correct) never
recognizing that a masked-to-EOF tail could itself hide a real section that
needed stripping. Each test below pins one of those specific failure modes.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))


def test_strip_ignores_a_heading_look_alike_inside_a_fenced_code_block():
    """External code review (medium, both `glm` and `openai` legs, converging):
    the section regex has no fence awareness, so a spec quoting a template or
    skill excerpt that itself contains a fenced `## Internal Plan Review`-shaped
    line would have that line mistaken for a real section boundary, silently
    deleting genuine spec content up to the next real heading."""
    from external_review_modes import strip_prior_review_sections

    spec_text = (
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Verification (medium+)\n"
        "Quoted template excerpt:\n"
        "```markdown\n"
        "## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** this is example template text, not a real review\n"
        "```\n"
        "Run tests after the quoted block above.\n\n"
        "## Acceptance Criteria\n- AC1: it works.\n"
    )
    result = strip_prior_review_sections(spec_text)
    assert "Run tests after the quoted block above." in result
    assert "## Acceptance Criteria" in result and "AC1: it works." in result
    assert "```markdown" in result, "the fence itself is untouched, only real sections strip"


def test_strip_ignores_a_heading_look_alike_inside_a_fence_with_a_longer_closer():
    """External code review, round 2 (medium, both `glm` and `openai` legs
    converged again): CommonMark allows a closing fence LONGER than the
    opener (``` opened, ```` closed is valid). A backreference-based masker
    demands an exact-length match, so a longer closer is never recognized —
    the whole block then goes unmasked and a heading-shaped line inside it
    is read as a real section boundary."""
    from external_review_modes import strip_prior_review_sections

    spec_text = (
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Verification (medium+)\n"
        "```\n"
        "## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** this is example template text, not a real review\n"
        "````\n"
        "Run tests after the quoted block above.\n\n"
        "## Acceptance Criteria\n- AC1: it works.\n"
    )
    result = strip_prior_review_sections(spec_text)
    assert "Run tests after the quoted block above." in result
    assert "## Acceptance Criteria" in result and "AC1: it works." in result


def test_strip_does_not_close_a_longer_fence_on_a_shorter_nested_marker():
    """External code review, round 3 (medium, `openai`): the prior fix's
    "any 3+ marker closes any opener" over-corrected — a 4-backtick block
    containing an inner 3-backtick line was closed early by that inner line,
    leaving the rest of the (still-open) block unmasked."""
    from external_review_modes import strip_prior_review_sections

    spec_text = (
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Verification (medium+)\n"
        "````\n"
        "some example fenced text\n"
        "```\n"
        "## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** this is example template text, not a real review\n"
        "````\n"
        "Run tests after the quoted block above.\n\n"
        "## Acceptance Criteria\n- AC1: it works.\n"
    )
    result = strip_prior_review_sections(spec_text)
    assert "Run tests after the quoted block above." in result
    assert "## Acceptance Criteria" in result and "AC1: it works." in result


def test_strip_masks_to_end_of_document_when_a_fence_is_never_closed():
    """External code review, round 3 (medium, `glm`): an opener with no
    matching closer must mask to end-of-document rather than leave its
    contents live for the section-finder to (wrongly) treat as a real
    section start. But masking to EOF has its own failure direction, caught
    by round 6 (`glm` + the local PR-review preflight, converging
    independently): if a heading-shaped line sits in that masked-to-EOF
    tail, nobody can tell from the text alone whether it is a harmless quote
    or a genuine prior-review section that needed stripping — silently
    passing it through either way risks a real rationale leak. `strip_prior_
    review_sections` now fails closed in that specific case instead of
    guessing (see `test_strip_raises_when_an_unterminated_fence_hides_a_real_
    heading`)."""
    from external_review_modes import UnstrippableSpecError, strip_prior_review_sections

    spec_text = (
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Verification (medium+)\n"
        "```\n"
        "## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** this is example template text, never closed\n"
    )
    with pytest.raises(UnstrippableSpecError):
        strip_prior_review_sections(spec_text)


def test_strip_raises_when_an_unterminated_fence_hides_a_real_heading():
    """External code review round 6 (medium, `glm`) + local PR-review
    preflight (BLOCK, same round): an unmatched fence opener earlier in a
    spec can mask a GENUINE, later `## Internal Plan Review` section from
    the section-finder — the section then survives unstripped, leaking its
    rationale into the architecture pass's input, the exact failure this
    whole module exists to prevent. Must fail closed rather than silently
    emit a spec that still carries it."""
    from external_review_modes import UnstrippableSpecError, strip_prior_review_sections

    spec_text = (
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Notes\n"
        "An accidental stray fence marker below (e.g. a copy-paste artifact):\n"
        "```\n"
        "some unrelated prose that was never meant to be a code block\n\n"
        "## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** rejected option B because Y — this is REAL rationale\n"
    )
    with pytest.raises(UnstrippableSpecError):
        strip_prior_review_sections(spec_text)


def test_strip_does_not_raise_when_an_unterminated_fence_hides_nothing_sensitive():
    """A legitimately unclosed fence with no heading-shaped line anywhere in
    its masked-to-EOF tail is not a risk — must pass through unchanged, not
    be refused defensively for content that was never in question."""
    from external_review_modes import strip_prior_review_sections

    spec_text = (
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Verification (medium+)\n"
        "```\n"
        "some ordinary example command that was never closed\n"
    )
    result = strip_prior_review_sections(spec_text)
    assert result == spec_text


def test_strip_masks_a_three_space_indented_fence():
    """External code review, round 3 (low, `glm`): CommonMark allows a fence
    opener indented up to 3 spaces; a column-0-only masker leaves an indented
    quote (e.g. inside a list item) unmasked."""
    from external_review_modes import strip_prior_review_sections

    spec_text = (
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Verification (medium+)\n"
        "1. Example item:\n"
        "   ```\n"
        "   ## Internal Plan Review (opus-plan-reviewer)\n"
        "   - **Findings:** example template text under a list item\n"
        "   ```\n"
        "Run tests after the indented block above.\n\n"
        "## Acceptance Criteria\n- AC1: it works.\n"
    )
    result = strip_prior_review_sections(spec_text)
    assert "Run tests after the indented block above." in result
    assert "## Acceptance Criteria" in result and "AC1: it works." in result


def test_strip_still_removes_a_real_prior_review_section_after_a_fence():
    """The fence-masking must not blind the strip to a REAL section that
    follows a fenced block earlier in the document."""
    from external_review_modes import strip_prior_review_sections

    spec_text = (
        "# Spec\n\n## Goal\nDo X.\n\n"
        "```markdown\nsome unrelated quoted snippet\n```\n\n"
        "## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** rejected option B because Y\n\n"
        "## Verification (medium+)\nRun tests.\n"
    )
    result = strip_prior_review_sections(spec_text)
    assert "rejected option B because Y" not in result
    assert "## Internal Plan Review" not in result
    assert "## Verification" in result and "Run tests." in result
    assert "some unrelated quoted snippet" in result


def test_strip_terminates_the_stripped_section_at_an_indented_or_tab_separated_heading():
    """External code review round 7 (medium, `openai`): the closing lookahead
    required an exact '\\n## ' (column 0, single space), so a legitimately
    indented following heading (a CommonMark ATX heading may carry up to 3
    spaces of indent) or one using a tab instead of a space after '##' was
    never recognized as the boundary — the real content of that FOLLOWING
    section was silently pulled into the deleted span along with the prior
    review."""
    from external_review_modes import strip_prior_review_sections

    indented = (
        "# Spec\n\n## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** rejected option B because Y\n\n"
        "   ## Acceptance Criteria\n- AC1: it works.\n"
    )
    result = strip_prior_review_sections(indented)
    assert "rejected option B because Y" not in result
    assert "## Acceptance Criteria" in result and "AC1: it works." in result

    tab_separated = (
        "# Spec\n\n## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** rejected option B because Y\n\n"
        "##\tVerification\nRun tests.\n"
    )
    result = strip_prior_review_sections(tab_separated)
    assert "rejected option B because Y" not in result
    assert "Verification" in result and "Run tests." in result


def test_strip_also_applies_on_the_plan_side_by_design():
    """External code review round 7 (low, `glm`): the strip runs on BOTH
    plan-side and iterate-side --mode architecture calls, and the plan side
    is only 'clean by construction' because the internal passes write to
    plan.md, never spec.md — nothing stops a hand-authored or adopted-
    template spec.md from carrying one of these headings for unrelated
    reasons. This documents that the strip removes it there too,
    intentionally, on this module's own 'err toward removing more, never
    toward leaking a real section' contract, rather than leaving that
    behavior untested and unreasoned-about."""
    from external_review_modes import strip_prior_review_sections

    spec_text = (
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Self-Review\nUnrelated content a template happened to carry.\n\n"
        "## Acceptance Criteria\n- AC1: it works.\n"
    )
    result = strip_prior_review_sections(spec_text)
    assert "Unrelated content a template happened to carry." not in result
    assert "## Acceptance Criteria" in result and "AC1: it works." in result

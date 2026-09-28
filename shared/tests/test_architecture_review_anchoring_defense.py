"""AC5 — the architecture pass's anchoring defense holds in code, not just prose.

`shared/prompts/architecture_reviewer/system`'s brief "deliberately does not
tell you which ones the author rejected, or why" — a promise the spec text
itself can break. Unlike the plan side's plan.md/spec.md split, the iterate
spec is the ONE document: `## Internal Plan Review` / `## Internal
Architecture Review` / `## Self-Review` all land in the very file handed to
this mode as --spec-file, each carrying the disposition-plus-reason the brief
exists to withhold. `strip_prior_review_sections` (external_review_modes.py)
is the code-level backstop; these tests prove it actually runs for
`--mode architecture` and is skipped for `--mode iterate`, where the
rejection rationale is intentionally shown (Stage-3 doubt review, high, D1).
"""

import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _SHARED / "scripts" / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


def _run_main_capturing_strip_calls(monkeypatch, spec, primary_file, mode, primary_flag):
    """In-process `main()` call with `strip_prior_review_sections` spied on.

    In-process (not subprocess) so the monkeypatch is visible — mirrors
    `test_main_iterate_mode_loads_iterate_prompts` in test_external_review_cli.py.
    Spies on the strip call directly, not on a provider call three steps
    downstream, so the assertion holds regardless of which provider branch a
    keyless run takes.
    """
    for key in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(spec.parent)
    import external_review
    real_strip = external_review.strip_prior_review_sections

    def spy(text):
        result = real_strip(text)
        seen.append(result)
        return result

    seen: list[str] = []
    monkeypatch.setattr(external_review, "strip_prior_review_sections", spy)
    plugin_root = spec.parent / "unused-plugin"
    plugin_root.mkdir(exist_ok=True)
    monkeypatch.setattr("sys.argv", [
        "external_review.py", "--mode", mode, "--spec-file", str(spec),
        primary_flag, str(primary_file), "--plugin-root", str(plugin_root),
        "--driver", "claude",
    ])
    rc = external_review.main()
    return rc, seen


def test_architecture_mode_strips_prior_review_sections_before_use(monkeypatch, tmp_path):
    """The architecture pass's anchoring defense (shared/prompts/architecture_reviewer
    /system: the brief "deliberately does not tell you which ones the author
    rejected, or why") depends on the spec not carrying that rationale. Unlike
    the plan side's plan.md/spec.md split, the iterate spec is the ONE document:
    `## Internal Plan Review` / `## Internal Architecture Review` / `## Self-Review`
    all land in the very file handed to this mode as --spec-file, each carrying
    the disposition-plus-reason the brief exists to withhold. A prose-only
    instruction does not stop that (Stage-3 doubt review, high)."""
    spec = tmp_path / "spec.md"
    brief = tmp_path / "architecture_brief.md"
    spec.write_text(
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** rejected option B because Y\n\n"
        "## Verification (medium+)\nRun tests.\n",
        encoding="utf-8",
    )
    brief.write_text("# Brief\n\n## Options on the table\n- A\n- B\n", encoding="utf-8")

    rc, seen = _run_main_capturing_strip_calls(monkeypatch, spec, brief, "architecture", "--brief-file")
    assert rc == 0
    assert seen, "strip_prior_review_sections was never called for --mode architecture"
    assert "Internal Plan Review" not in seen[-1]
    assert "rejected option B because Y" not in seen[-1]
    assert "## Goal" in seen[-1] and "Do X." in seen[-1], "unrelated sections must survive"


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
    matching closer must mask to end-of-document. Unmasked, the quoted
    heading-look-alike would be read by `_PRIOR_REVIEW_SECTION_RE` as a REAL
    section start and everything from it to EOF would be stripped out as
    if it were genuine rejection rationale. Masked, the section-finder never
    sees it, so nothing is stripped and the document passes through whole —
    the failure direction every fence fix here must avoid is a hidden
    section boundary, never a little extra masked (but preserved) text."""
    from external_review_modes import strip_prior_review_sections

    spec_text = (
        "# Spec\n\n## Goal\nDo X.\n\n"
        "## Verification (medium+)\n"
        "```\n"
        "## Internal Plan Review (opus-plan-reviewer)\n"
        "- **Findings:** this is example template text, never closed\n"
    )
    result = strip_prior_review_sections(spec_text)
    assert result == spec_text, (
        "an unclosed fence must mask its heading-look-alike from the "
        "section-finder, not have it mistaken for a real section and "
        "stripped along with everything after it"
    )


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


def test_iterate_mode_does_not_strip_prior_review_sections(monkeypatch, tmp_path):
    """Iterate mode intentionally shows the mini-plan's own rejection rationale
    — only architecture mode's anchoring defense needs the strip."""
    spec = tmp_path / "spec.md"
    plan = tmp_path / "mini-plan.md"
    spec.write_text(
        "# Spec\n\n## Internal Plan Review (opus-plan-reviewer)\nkept\n",
        encoding="utf-8",
    )
    plan.write_text("# Mini-plan\nStep 1.", encoding="utf-8")

    rc, seen = _run_main_capturing_strip_calls(monkeypatch, spec, plan, "iterate", "--plan-file")
    assert rc == 0
    assert not seen, "iterate mode must not call the architecture-only strip"

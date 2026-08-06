"""What the SHIPPED architecture prompts and brief template must say.

Separated from `test_architecture_review_mode.py`, which owns the CLI's
behaviour (arg validation, placeholder rendering, envelope shape). These assert
content: that the prompt files exist at all, that they state the rules the pass
depends on, and that they ask for findings in the shape the parser reads. A
prompt that loads fine and says the wrong thing breaks the pass without breaking
a single CLI test.
"""

from pathlib import Path

import pytest

from lib.external_review_prompts import (
    VERDICT_INSTRUCTION,
    default_review_prompts,
    load_architecture_review_prompts,
)

_SHARED = Path(__file__).resolve().parents[1]


# ---- AC2: the shipped prompts ----------------------------------------------

def test_architecture_prompts_ship_and_are_non_empty():
    """Both files MUST ship — the inline default is a fallback, not the design.

    Mirrors the same assertion the iterate prompts carry: a graceful-empty
    loader would let a deleted prompt directory degrade into the one-sentence
    inline default without anything going red.
    """
    system, user = load_architecture_review_prompts()
    assert system, "shared/prompts/architecture_reviewer/system must ship"
    assert user, "shared/prompts/architecture_reviewer/user must ship"
    assert "{BRIEF}" in user
    assert "{SPEC}" in user


def test_architecture_system_prompt_states_the_withholding():
    """The reviewer must be TOLD the rejection reasons were withheld.

    Without that sentence the model fills the gap itself — it assumes the
    author had reasons it was not shown and hedges, which is the same
    deference the anchoring was supposed to remove.
    """
    system, _ = load_architecture_review_prompts()
    lowered = system.lower()
    assert "reject" in lowered
    assert "not a mistake" in lowered or "not a defect" in lowered, (
        "the prompt must explicitly bless recommending an option the author "
        "already discarded, or the reviewer hedges instead of answering"
    )
    assert "SHIPWRIGHT_VERDICT" in system


def test_architecture_user_template_pulls_no_plan():
    """The template must not reach for the plan by any name.

    Raised by the external plan review of this very change (openai, high): a
    user template that interpolated the mini-plan alongside the brief would
    hand the reviewer the rejection rationale the brief exists to withhold —
    and every other assertion here would still pass, because the emitted
    envelope is byte-identical either way.
    """
    _, user = load_architecture_review_prompts()
    assert "{PLAN}" not in user and "{DIFF}" not in user
    lowered = user.lower()
    for banned in ("mini-plan", "implementation plan", "rejected because"):
        assert banned not in lowered, (
            f"the architecture user template references {banned!r} — this pass "
            "reads a brief, and the plan's own reasoning is what it withholds"
        )


@pytest.mark.parametrize("source", ["file", "default"])
def test_architecture_prompt_mandates_the_parseable_finding_labels(source):
    """Findings must be asked for in the shape `review_prose._KEY_RE` reads.

    Found by running this pass for real: the first prompt asked for "severity +
    finding + the concrete alternative" as prose, both reviewers obliged with
    `- **Low severity.** …`, and the recorder itemized ZERO of five findings —
    `parse_status: unstructured`, `findings_count: 0`. The row was honest (the
    caveat travels in `reason`) and useless. Pinned for the on-disk prompt AND
    the inline default, because a prompt-directory outage must not silently
    reintroduce the unparseable shape.
    """
    # Checked over system+user together: the on-disk prompt carries the output
    # format in `system`, the inline default carries it in `user`. Which half
    # states it is a layout choice; that the model is asked for it is not.
    prompt = "\n".join(load_architecture_review_prompts() if source == "file"
                       else default_review_prompts("architecture"))
    for label in ("Category:", "Severity:", "Finding:", "Suggestion:"):
        assert label in prompt, (
            f"the architecture prompt must ask for {label!r} verbatim — "
            "lib/review_prose parses findings by those labels and discards "
            "prose written without them"
        )


def test_architecture_prompts_explicit_root(tmp_path):
    d = tmp_path / "architecture_reviewer"
    d.mkdir()
    (d / "system").write_text("sys", encoding="utf-8")
    (d / "user").write_text("{SPEC}{BRIEF}", encoding="utf-8")
    assert load_architecture_review_prompts(tmp_path) == ("sys", "{SPEC}{BRIEF}")


def test_architecture_prompts_missing_returns_empty(tmp_path):
    assert load_architecture_review_prompts(tmp_path) == ("", "")


def test_architecture_inline_default_carries_the_verdict_instruction():
    """A run that fell back to the default must not silently lose the verdict.

    The verdict line is what makes two reviewers comparable; the same rule
    already binds the other three modes.
    """
    system, user = default_review_prompts("architecture")
    assert system.endswith(VERDICT_INSTRUCTION)
    assert "{BRIEF}" in user
    assert "{SPEC}" in user


# ---- AC7: the brief template ------------------------------------------------

def test_brief_template_ships_with_the_anti_anchoring_rule():
    """The template is the only place the rule is stated to the human writing
    the brief. If it stops saying it, the next author copies the mini-plan's
    rejection rationale in and the pass quietly becomes a plan review."""
    template = _SHARED / "templates" / "architecture_brief.md"
    assert template.exists()
    text = template.read_text(encoding="utf-8")
    assert "Do NOT give the reasons any of them were rejected" in text
    assert "Options on the table" in text
    assert "Nothing. This changes machinery that already exists" in text, (
        "the three-line shape for a change that adds nothing permanent is what "
        "keeps an unconditional pass affordable — without it the brief becomes "
        "a per-run authoring tax and the pass becomes the ritual it must not be"
    )

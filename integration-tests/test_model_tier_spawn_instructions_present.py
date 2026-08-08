"""Drift-protection: model-tier flag + spawn-instruction anchors in both
`iterate` and `build` SKILL.md files.

Cross-plugin by nature (touches `plugins/shipwright-iterate` AND
`plugins/shipwright-build`), so it lives in `integration-tests/`, not either
plugin's own `tests/` — the repo's one-test-root rule means a plugin's own
test root cannot import from a sibling plugin's tree.

Mirrors `plugins/shipwright-iterate/tests/test_skill_step_6_rules_present.py`'s
anchor-based approach: search for stable, normalized markers rather than
whole prose blocks, so the test survives benign rewording but fails when the
flag or the spawn-time `model=` instruction disappears entirely.

See .shipwright/planning/iterate/2026-08-07-agent-model-tiers.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

ITERATE_SKILL_MD = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "SKILL.md"
)
BUILD_SKILL_MD = (
    REPO_ROOT / "plugins" / "shipwright-build" / "skills" / "build" / "SKILL.md"
)
ITERATION_PLANNING_MD = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "references"
    / "iteration-planning.md"
)
STEP_5_EXTERNAL_REVIEW_MD = (
    REPO_ROOT / "plugins" / "shipwright-plan" / "skills" / "plan" / "references"
    / "step-5-external-review.md"
)

# (skill file, flag anchors expected in the banner usage line)
FLAG_ANCHORS = (
    (ITERATE_SKILL_MD, ("--review-model", "--finalization-model", "--plan-review-model")),
    (BUILD_SKILL_MD, ("--review-model", "--finalization-model", "--execution-model")),
)

# (skill file, spawn-time `model=` instruction anchor). iterate's own
# SKILL.md carries the genuine spawn line directly; build's SKILL.md was
# trimmed under its 300-line cap to a pointer, so build has no entry here —
# its actual `model=` spawn sites live one level down, in the reference
# files SKILL.md points to, and are anchored on the real phrase (not a
# heading) by test_build_reference_files_carry_the_model_tier_note below.
SPAWN_ANCHORS = (
    (ITERATE_SKILL_MD, "Pass `model=<the review tier resolved in §F>`"),
    # The two `plan_review`-role spawn sites this diff adds (AC-4/AC-6):
    # /shipwright-plan Step 5-int and /shipwright-iterate's own internal
    # Plan Review sub-step. Both spawn `opus-plan-reviewer` with the same
    # phrase; without this anchor, deleting either `model=` instruction
    # leaves the full suite green (a silent no-op regression).
    (ITERATION_PLANNING_MD, "Agent tool's `model=`"),
    (STEP_5_EXTERNAL_REVIEW_MD, "Agent tool's `model=`"),
)


@pytest.mark.parametrize("skill_md", [ITERATE_SKILL_MD, BUILD_SKILL_MD])
def test_skill_md_exists(skill_md: Path) -> None:
    assert skill_md.is_file(), f"SKILL.md not found at {skill_md}"


@pytest.mark.parametrize("skill_md,flags", FLAG_ANCHORS)
def test_model_tier_flags_present_in_banner(skill_md: Path, flags: tuple[str, ...]) -> None:
    text = skill_md.read_text(encoding="utf-8")
    for flag in flags:
        assert flag in text, (
            f"{skill_md} is missing the {flag!r} usage-banner flag. "
            "If this flag was deliberately removed or renamed, update "
            "FLAG_ANCHORS in this test and the iterate spec's ACs."
        )


@pytest.mark.parametrize("skill_md,anchor", SPAWN_ANCHORS)
def test_spawn_time_model_instruction_present(skill_md: Path, anchor: str) -> None:
    text = skill_md.read_text(encoding="utf-8")
    assert anchor in text, (
        f"{skill_md} is missing the spawn-time model-tier instruction. "
        f"Expected to find: {anchor!r}. Without this, the resolved tier is "
        "computed but never reaches an Agent-tool spawn — a silent no-op."
    )


def test_build_skill_md_points_to_tier_resolution() -> None:
    """build's SKILL.md itself only computes the tiers (§G) and points at the
    reference files that spawn with them — it carries no `model=` phrase of
    its own, unlike iterate's. This only guards the pointer exists; the
    actual spawn wiring is guarded by test_build_reference_files_carry_the_model_tier_note."""
    text = BUILD_SKILL_MD.read_text(encoding="utf-8")
    assert "Resolve model tiers first" in text, (
        "build SKILL.md's §G lost its pointer to the Model tiers section in "
        "references/first-actions.md"
    )


def test_build_reference_files_carry_the_model_tier_note() -> None:
    """The three build-side spawn sites this diff wires (review cascade,
    section-builder, browser-fixer) each carry a genuine `model=` phrase —
    not just a heading that could survive the phrase's own deletion — one
    level below SKILL.md, in the reference files SKILL.md points to."""
    build_refs = REPO_ROOT / "plugins" / "shipwright-build" / "skills" / "build" / "references"
    checks = {
        "code-review.md": "model=<the review tier resolved at SKILL.md §G>",
        "autonomous-loop.md": 'model=<finalization tier resolved at SKILL.md §G, omit if "inherit">',
        "browser-verify.md": "model=<execution tier resolved at SKILL.md §G>",
    }
    for filename, anchor in checks.items():
        text = (build_refs / filename).read_text(encoding="utf-8")
        assert anchor in text, f"{filename} is missing the {anchor!r} model= spawn anchor"


def test_iterate_reference_files_carry_the_model_tier_note() -> None:
    """iterate-side spawn sites: the standalone cascade pointer and the
    campaign-delegated cascade + sub-iterate-runner spawn — anchored on the
    genuine `model=` phrase in each file, not a loose heading/description."""
    iterate_refs = (
        REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "references"
    )
    checks = {
        "iteration-reviews.md": "the `review` tier resolved at this skill's",
        "campaign-mode.md": 'model=<finalization tier resolved at loop step 2, omit if "inherit">',
    }
    for filename, anchor in checks.items():
        text = (iterate_refs / filename).read_text(encoding="utf-8")
        assert anchor in text, f"{filename} is missing the {anchor!r} model-tier anchor"
    campaign_text = (iterate_refs / "campaign-mode.md").read_text(encoding="utf-8")
    assert "Pass `model=<review tier resolved at loop step 2>`" in campaign_text, (
        "campaign-mode.md's delegated review-cascade spawn (step 3f-bis) lost "
        "its model= instruction"
    )


def test_standalone_record_template_carries_model_tier_flag() -> None:
    """The canonical `record_review_pass.py record` template a session copies
    verbatim for the standalone (non-campaign) path must itself carry
    `--model-tier` — a heading pointing at the note elsewhere is not enough
    if the copy-paste block a session actually runs omits the flag."""
    iterate_refs = (
        REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "references"
    )
    text = (iterate_refs / "iteration-reviews.md").read_text(encoding="utf-8")
    assert "--model-tier" in text, (
        "iteration-reviews.md's standalone record template is missing "
        "--model-tier — the recorded reviews.json entry would never carry "
        "the resolved tier on the non-campaign path"
    )

"""Drift-protection tests for the P3.1 reviewer-stack orchestration.

Iterate `iterate-2026-05-30-reviewer-stack` (SP1 + OS3) adds two NEW reviewer
subagents (`spec-reviewer`, `doubt-reviewer`) alongside `code-reviewer` and
orchestrates a three-stage cascade in build Step 6:

    spec-reviewer (HARD-GATE) -> code-reviewer (quality) -> doubt-reviewer (cond.)

The intent's acceptance criteria are *behavioral* (live subagents) and cannot be
asserted from pytest. This test pins the **structural contract** the behavior
follows from: the prompts must carry the right tags, biases, trigger heuristic,
gating semantics, and attribution, and the orchestration doc must encode the
cascade order + conditional gate. Style mirrors `test_skill_references_link.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
# Paths
BUILD_PLUGIN = Path(__file__).resolve().parent.parent
AGENTS_DIR = BUILD_PLUGIN / "agents"
BUILD_SKILL_DIR = BUILD_PLUGIN / "skills" / "build"

SPEC_REVIEWER = AGENTS_DIR / "spec-reviewer.md"
DOUBT_REVIEWER = AGENTS_DIR / "doubt-reviewer.md"
CODE_REVIEWER = AGENTS_DIR / "code-reviewer.md"
CODE_REVIEW_REF = BUILD_SKILL_DIR / "references" / "code-review.md"
KERN_SKILL = BUILD_SKILL_DIR / "SKILL.md"

# The three reviewer prompts that make up the cascade.
ALL_REVIEWERS = [SPEC_REVIEWER, CODE_REVIEWER, DOUBT_REVIEWER]

RUNTIME_PROMPT_LOC_LIMIT = 400


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _lower(path: Path) -> str:
    return _read(path).lower()


def _loc(path: Path) -> int:
    return sum(1 for _ in _read(path).splitlines())

# Existence

@pytest.mark.parametrize(
    "path",
    [SPEC_REVIEWER, DOUBT_REVIEWER],
    ids=["spec-reviewer", "doubt-reviewer"],
)
def test_new_reviewer_agent_exists(path: Path) -> None:
    assert path.is_file(), f"new reviewer agent missing: {path}"


@pytest.mark.parametrize(
    "path",
    ALL_REVIEWERS,
    ids=["spec-reviewer", "code-reviewer", "doubt-reviewer"],
)
def test_reviewer_has_frontmatter_name(path: Path) -> None:
    """Each reviewer must declare a `name:` matching its filename stem so the
    plugin agent-discovery resolves it (Claude Code auto-discovers agents/*.md).
    """
    text = _read(path)
    stem = path.stem  # e.g. "spec-reviewer"
    assert f"name: {stem}" in text, (
        f"{path.name} must declare frontmatter `name: {stem}`"
    )

# spec-reviewer — HARD-GATE spec-compliance (SP1, Superpowers two-stage)

def test_spec_reviewer_is_hard_gate() -> None:
    text = _read(SPEC_REVIEWER)
    assert "HARD-GATE" in text or "HARD GATE" in text, (
        "spec-reviewer must carry a HARD-GATE tag (Superpowers style) — it "
        "blocks the code-reviewer stage until spec-compliance passes."
    )


def test_spec_reviewer_cites_spec_line_on_reject() -> None:
    low = _lower(SPEC_REVIEWER)
    # Adversarial spec-compliance: a REJECT must cite the specific spec
    # line/section the divergence violates.
    assert "reject" in low, "spec-reviewer must emit a REJECT verdict"
    assert "pass" in low, "spec-reviewer must emit a PASS verdict"
    assert any(tok in low for tok in ("cite", "citation", "spec line", "line/section", "section")), (
        "spec-reviewer must require an explicit spec-line/section citation on REJECT"
    )


def test_spec_reviewer_is_adversarial_compliance() -> None:
    low = _lower(SPEC_REVIEWER)
    assert "spec" in low and "compliance" in low, (  # artifact-path-canon: legacy
        "spec-reviewer must frame itself as a spec-compliance review"
    )

# doubt-reviewer — disprove-biased fresh-context (OS3, Osmani doubt-driven)

def test_doubt_reviewer_is_disprove_biased() -> None:
    low = _lower(DOUBT_REVIEWER)
    assert "disprove" in low, (
        "doubt-reviewer must be biased to DISPROVE the change (Osmani "
        "doubt-driven). Phrase 'disprove' must appear."
    )


def test_doubt_reviewer_is_fresh_context() -> None:
    low = _lower(DOUBT_REVIEWER)
    assert "fresh context" in low or "fresh-context" in low, (
        "doubt-reviewer must run in a fresh context (no inheritance of the "
        "implementer's assumptions)."
    )


@pytest.mark.parametrize(
    "trigger",
    ["migration", "async", "concurrency", "cross-plugin", "irreversible"],
)
def test_doubt_reviewer_documents_trigger_heuristic(trigger: str) -> None:
    """doubt-reviewer fires only for non-trivial decisions. The trigger
    heuristic (migrations, async/concurrency, cross-plugin imports,
    irreversible ops) must be spelled out in its own prompt.
    """
    low = _lower(DOUBT_REVIEWER)
    assert trigger in low, (
        f"doubt-reviewer must document the '{trigger}' trigger in its heuristic"
    )


def test_doubt_reviewer_is_advisory_must_address() -> None:
    low = _lower(DOUBT_REVIEWER)
    assert "advisory" in low, (
        "doubt-reviewer must mark itself ADVISORY (not a hard blocker) — only "
        "spec-reviewer is a hard gate (interview Q2)."
    )
    assert "must" in low and ("address" in low or "respond" in low or "rebut" in low), (
        "doubt-reviewer must require the implementer to address/respond to each "
        "objection in writing (advisory-must-address)."
    )


def test_doubt_reviewer_not_a_hard_block() -> None:
    """Guard the Q2 decision: a reasoned rebuttal may proceed. The prompt must
    not claim to hard-block commit the way spec-reviewer does.
    """
    low = _lower(DOUBT_REVIEWER)
    assert "rebuttal" in low or "reasoned response" in low or "may proceed" in low, (
        "doubt-reviewer must allow a reasoned rebuttal to proceed to commit"
    )

# MIT attribution footers — all three reviewers (intent acceptance)

@pytest.mark.parametrize(
    "path",
    ALL_REVIEWERS,
    ids=["spec-reviewer", "code-reviewer", "doubt-reviewer"],
)
def test_reviewer_carries_mit_attribution(path: Path) -> None:
    low = _lower(path)
    assert "mit" in low, f"{path.name} must carry an MIT attribution footer"


def test_spec_reviewer_attributes_superpowers() -> None:
    low = _lower(SPEC_REVIEWER)
    assert "obra/superpowers" in low, (
        "spec-reviewer (SP1) must attribute obra/superpowers"
    )
    assert "jesse vincent" in low, "spec-reviewer must credit © Jesse Vincent"


def test_doubt_reviewer_attributes_osmani() -> None:
    low = _lower(DOUBT_REVIEWER)
    assert "addyosmani/agent-skills" in low, (
        "doubt-reviewer (OS3) must attribute addyosmani/agent-skills"
    )
    assert "addy osmani" in low, "doubt-reviewer must credit © Addy Osmani"

# Orchestration — cascade order + conditional gate (references/code-review.md)

def test_orchestration_documents_cascade_order() -> None:
    """code-review.md must encode spec-reviewer BEFORE code-reviewer BEFORE
    doubt-reviewer (the AC-4 / AC-5 ordering).

    Pin the order on a SINGLE line (the overview arrow line), not just by
    first-occurrence across the whole doc — a later section could otherwise
    contradict the order and the test would still pass.
    """
    low = _lower(CODE_REVIEW_REF)
    for name in ("spec-reviewer", "code-reviewer", "doubt-reviewer"):
        assert name in low, f"code-review.md must mention {name}"
    ordered_line = next(
        (
            line for line in low.splitlines()
            if "spec-reviewer" in line and "code-reviewer" in line
            and "doubt-reviewer" in line
            and line.index("spec-reviewer") < line.index("code-reviewer") < line.index("doubt-reviewer")
        ),
        None,
    )
    assert ordered_line is not None, (
        "code-review.md must state the cascade order on a single line "
        "(spec-reviewer -> code-reviewer -> doubt-reviewer), e.g. the overview arrow."
    )


def test_orchestration_spec_gate_blocks_code_review() -> None:
    """AC-4: on spec REJECT, code-reviewer is NOT invoked until spec PASS.

    Assert the ACTUAL blocking contract, not just loose keywords — a doc that
    merely mentions "hard gate" but lets Stage 2 run on REJECT must fail.
    """
    low = _lower(CODE_REVIEW_REF)
    assert "hard-gate" in low or "hard gate" in low, (
        "code-review.md must describe the spec-reviewer HARD-GATE"
    )
    assert "not invoked until" in low and "pass" in low, (
        "code-review.md must state the code-reviewer is NOT invoked until the "
        "spec-reviewer returns PASS (the real hard-gate contract, AC-4)"
    )
    assert "re-review" in low or "rereview" in low, (
        "code-review.md must describe the spec re-review loop"
    )


def test_orchestration_doubt_conditional_heuristic() -> None:
    """AC-5: doubt-reviewer fires for migrations but not for docs-only diffs."""
    low = _lower(CODE_REVIEW_REF)
    assert "migration" in low, (
        "code-review.md must document the migrations trigger for doubt-reviewer"
    )
    # Docs-only / trivial change is the excluded branch.
    assert "trivial" in low or "readme" in low or "docs-only" in low or "documentation-only" in low, (
        "code-review.md must document that trivial/docs-only diffs skip doubt-reviewer"
    )


def test_orchestration_doubt_runs_after_code_review() -> None:
    low = _lower(CODE_REVIEW_REF)
    assert "after" in low, (
        "code-review.md must state doubt-reviewer runs AFTER code-reviewer passes"
    )


def test_orchestration_reviewers_internal_only() -> None:
    """Interview Q1: the new reviewers are internal-only; the external cascade
    (6c) stays a generic code-quality second opinion.
    """
    low = _lower(CODE_REVIEW_REF)
    assert "internal" in low, (
        "code-review.md must record the internal-only decision for the new reviewers"
    )


def test_kern_skill_points_to_cascade() -> None:
    """The build Kern Step 6 must point at the cascade so the agent loads it."""
    low = _lower(KERN_SKILL)
    assert "spec-reviewer" in low and "doubt-reviewer" in low, (
        "build SKILL.md Step 6 must name the spec-reviewer and doubt-reviewer stages"
    )

# Bloat budgets (AC-8)

@pytest.mark.parametrize(
    "path",
    ALL_REVIEWERS,
    ids=["spec-reviewer", "code-reviewer", "doubt-reviewer"],
)
def test_reviewer_under_runtime_prompt_budget(path: Path) -> None:
    loc = _loc(path)
    assert loc <= RUNTIME_PROMPT_LOC_LIMIT, (
        f"{path.name} is {loc} LOC, must be <= {RUNTIME_PROMPT_LOC_LIMIT} "
        "(runtime-prompt budget; no fresh grandfathering)."
    )


def test_build_kern_still_under_300_loc() -> None:
    """Adding the Step 6 cascade pointer must NOT push the Kern over its cap."""
    loc = _loc(KERN_SKILL)
    assert loc <= 300, (
        f"build Kern SKILL.md is {loc} LOC, must stay <= 300 — push orchestration "
        "detail into references/code-review.md, not the Kern."
    )

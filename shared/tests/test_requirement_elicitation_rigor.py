"""Drift protection for the elicitation method's RIGOR rules (REQ-3 Phase 2).

Sibling of ``test_requirement_elicitation_refs.py``. The seam is real rather
than a size dodge: that module asks *does the shared module still exist and is
it still cited* — a pointer-integrity question. This one asks *does it still
demand the things that make elicitation actually rigorous* — a content question,
and every rule here was written because the method failed without it during the
REQ-3 Phase 2 content round.

Each test names the finding it descends from, because a bare assertion here
reads as pedantry; the failure it prevents is the point. All five were found by
dogfooding the module on this repo's own requirements catalog, which is exactly
what campaign decision D13 said Phase 2 was for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "shared" / "requirement-elicitation.md"


def test_outcome_is_the_spine_and_does_not_displace_the_other_dimensions():
    """REQ-3 Phase 2 finding 4 — the dogfooding round's most valuable result.

    Every criterion the round first produced described how a phase BEHAVES and
    none described what must EXIST afterwards. Criteria like that read as
    thorough and verify nothing: a phase can follow every step and still emit an
    empty or incomplete artifact.

    Both halves are pinned, because each fails differently. Drop the spine rule
    and the dimension decays back into one row nobody weights. Drop the
    does-not-displace rule and the correction over-swings into banning the
    boundary and failure criteria, which are real guarantees (operator, on
    reading the first draft of this fix: "es sollte nicht das eine oder andere
    sein").
    """
    body = MODULE.read_text(encoding="utf-8")
    start = body.index("## 8. The coverage checklist")
    end = body.index("## 9.", start)
    section = body[start:end].lower()

    assert "what must exist afterwards" in section, (
        "§8 must ask the outcome question in words — 'what must exist afterwards "
        "for this to have succeeded?' — not merely name a dimension"
    )
    assert "spine" in section, (
        "§8 must mark Outcome as the spine: criteria that describe only the "
        "workflow are incomplete"
    )
    assert "does not displace" in section, (
        "§8 must state that Outcome ADDS to the other dimensions rather than "
        "replacing them — boundaries, edge cases and failure behaviour stay"
    )


def test_module_carries_the_negative_space_pass():
    """§8.1 — REQ-3 Phase 2 finding 3.

    The checklist verifies the recorded context is complete; it cannot tell you
    the capability itself is under-specified. Found empirically: FR-01.02
    promised two capabilities and had criteria for neither, while passing every
    other dimension.
    """
    body = MODULE.read_text(encoding="utf-8")
    assert "### 8.1 The negative-space pass" in body, "§8.1 negative-space pass is gone"
    assert "should this capability guarantee that it currently does not" in body, (
        "keep the inverse question verbatim — it is the whole point of §8.1"
    )


def test_assumed_is_only_for_unobtainable_answers():
    """§8 — REQ-3 Phase 2 finding 5, the one actively causing harm.

    The Phase-1 wording permitted `Basis: assumed` UNCONDITIONALLY, so an agent
    could mark every dimension assumed and remain formally compliant with the
    method. In greenfield — where the person who knows is in the conversation —
    that is not honesty, it is declining to ask, which is precisely the
    generate-something-plausible failure this module exists to prevent.

    Pinned per-surface because the rule is deliberately ASYMMETRIC: brownfield
    genuinely cannot obtain the answers, so `assumed` stays available there,
    against a work item.
    """
    body = MODULE.read_text(encoding="utf-8")
    lower = body.lower()

    assert "cannot be obtained" in lower, (
        "the stop-condition must gate `assumed` on the answer being UNOBTAINABLE"
    )
    assert "declining to ask" in lower, (
        "keep the naming of the failure mode — marking assumed while someone "
        "could answer is declining to ask, not honesty"
    )
    # Greenfield: the person is present, so `assumed` is closed.
    start = body.index("## 12. How each plugin applies it")
    twelve = body[start:].lower()
    assert "`assumed` is not available" in twelve, (
        "§12 must close `assumed` for /shipwright-project — the person is present"
    )
    # Brownfield: available, but it must schedule its own repayment.
    assert "work item" in twelve, (
        "§12 must require an adopt-derived `assumed` requirement to raise a work "
        "item to confirm it, so it is scheduled debt not a permanent guess"
    )


@pytest.mark.covers("FR-01.02/AC11")
def test_module_requires_hard_to_reverse_rationale_linked_from_the_requirement():
    """FR-01.02 #8 (req3-06-enforcement-mono, sub-iterate e2): "Hard-to-reverse
    rationale recorded + linked." The floor half — an ADR exists for the
    phase at all — is code-enforced (C4, `project_checks.check_c4_decision_log_has_phase_adr`).
    The LINK-BACK half (a specific ADR traceable from the specific
    requirement it justifies) has no addressable field anywhere in the
    FR-row schema to check mechanically — fr-authoring.md defines no
    "links to ADR-NNN" cell, and inventing one is a schema change, not a
    check. Per the campaign's own abort condition (no deterministic oracle
    → downgrade to judgement + drift test, never a weaker gate that pretends),
    this is the honest ceiling: pin that §7 still demands the link in prose.
    """
    body = MODULE.read_text(encoding="utf-8")
    assert "linked from the" in body, (
        "§7 must still say the hard-to-reverse *why* is linked FROM the "
        "requirement — the promise FR-01.02 #8's ledger row names"
    )
    assert "an ADR, linked" in body, (
        "§8's coverage-checklist Rationale row must still require the ADR "
        "to be linked, not merely written"
    )


@pytest.mark.covers("FR-01.16/AC10")
def test_module_separates_enforced_from_prompt_only():
    """§6 — REQ-3 Phase 2 finding 2.

    Found the expensive way: six requirements were 'verified' by reading the
    SKILL.md prose that asserts the same claim. A prompt is the claim under
    test, not evidence for it. The three-way verdict decides what can ever be
    tested, so the test-backfill track is not sent hunting for oracles that
    cannot exist.
    """
    body = MODULE.read_text(encoding="utf-8")
    lower = body.lower()
    assert "reading a prompt is not reading the code" in lower, (
        "§6 must state that an instruction file is the claim under test"
    )
    for verdict in ("enforced", "prompt-only", "contradicted"):
        assert verdict in lower, f"§6 three-way verdict is missing {verdict!r}"
    assert "no behavioural test is possible" in lower, (
        "§6 must say a prompt-only guarantee admits only a drift test — the "
        "distinction the enforcement campaign depends on"
    )


SPEC_GENERATION = (
    REPO_ROOT / "plugins" / "shipwright-project" / "skills" / "project"
    / "references" / "spec-generation.md"
)


@pytest.mark.covers("FR-01.02/AC05")
def test_spec_generation_requires_criteria_before_a_requirement_finishes():
    """FR-01.02 AC05: no requirement leaves the phase unelaborated. Nothing
    mechanically enforces this today (`criteria_free_of_implementation_detail`
    scores criteria CONTENT but vacuously passes a row with zero criteria —
    see `test_criteria_free_of_implementation_detail_passes_when_no_criteria_anchored`
    in `test_project_gate_extras.py`), so this is a prompt-only guarantee per
    `requirement-elicitation.md` §6 — pin the instruction itself, not a
    behaviour no gate exists to check."""
    body = SPEC_GENERATION.read_text(encoding="utf-8")
    assert "Every FR with Priority \"Must\" MUST have acceptance criteria" in body, (
        "spec-generation.md must still obligate every Must-priority "
        "requirement to carry acceptance criteria before the phase finishes"
    )


@pytest.mark.covers("FR-01.16/AC06")
def test_module_requires_adr_capture_at_the_decision_moment():
    """FR-01.16 AC06: a hard-to-reverse, surprising, genuine-trade-off choice
    is captured AS A DECISION RECORD at the moment it is made, and the
    project's domain vocabulary lives in a plain glossary carrying no
    implementation detail. Pin §7's rule sentence, not just its heading."""
    normalized = " ".join(MODULE.read_text(encoding="utf-8").split())
    assert (
        "the *why* behind a hard-to-reverse choice is captured at the moment "
        "it is decided" in normalized
    ), "§7 must still say the ADR is captured AT THE MOMENT the choice is made"
    assert "totally devoid of implementation detail" in normalized, (
        "§7 must still require CONTEXT.md to carry no implementation detail"
    )


@pytest.mark.covers("FR-01.16/AC08")
def test_module_requires_confirmation_before_writing_the_requirement():
    """FR-01.16 AC08: coverage complete -> play back the shared understanding
    and wait for the person's confirmation before writing anything; skipping
    it means recording a guess, not the agreed requirement. Pin §9's rule
    sentence, not just its heading."""
    normalized = " ".join(MODULE.read_text(encoding="utf-8").split())
    assert "Do not act on it until I confirm we have reached a shared understanding" in normalized, (
        "§9 must still open with Pocock's confirm-before-acting instruction"
    )
    assert (
        "The confirmation is the hand-off from *their* mental model to *the "
        "recorded one*" in normalized
    ), "§9 must still name confirmation as the hand-off from their model to the recorded one"

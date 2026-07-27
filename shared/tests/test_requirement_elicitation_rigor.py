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

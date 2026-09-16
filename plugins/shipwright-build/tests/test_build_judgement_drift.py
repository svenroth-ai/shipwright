"""Drift tests for FR-01.05's two judgement rows — campaign decision D7
(req3-06-enforcement-mono, sub-iterate e6).

The AC-evidence ledger (`.shipwright/planning/campaigns/2026-07-23-req3-ac-
evidence-ledger-mono.md`, FR-01.05 #2/#3) classifies both as
`prompt-only (judgement)`: whether a diff "does exactly what the section
specified" (AC03) or "matches its design mockup" (AC04) is a reading
question the spec-reviewer subagent answers by comparing prose to a diff —
no deterministic oracle exists, so D7 forbids a gate. The honest ceiling is
a drift test pinning that spec-reviewer.md still instructs the check.

A failure here means the governing instruction changed — that is a prompt
to update the pinned text to the new instruction, never a reason to delete
the test (this exact failure mode is why 6 of the ledger's 25 judgement
rows had real coverage nobody could find: an earlier edit moved the prose
and nothing caught it).
"""

from __future__ import annotations

from pathlib import Path

import pytest

SPEC_REVIEWER = (
    Path(__file__).resolve().parent.parent / "agents" / "spec-reviewer.md"
)


@pytest.mark.covers("FR-01.05/AC03")
def test_spec_reviewer_still_checks_faithful_and_in_scope():
    """FR-01.05 AC03: every acceptance criterion is met, none silently
    skipped or downgraded, and nothing outside the section's scope is
    added. Pin the two questions that together make up this criterion —
    'Faithful?' (nothing quietly weakened) and 'In-scope?' (nothing extra
    added) — not just their heading words.
    """
    normalized = " ".join(SPEC_REVIEWER.read_text(encoding="utf-8").split())
    assert "**Faithful?**" in normalized, (
        "spec-reviewer.md must still ask whether the code does what the "
        "requirement SAYS, not a near-neighbour — the none-skipped/"
        "none-downgraded half of AC03"
    )
    assert "each is a divergence" in normalized, (
        "the divergence examples (renamed fields, relaxed validation, a "
        "skipped edge case) must still be named as divergences, not notes"
    )
    assert "**In-scope?**" in normalized, (
        "spec-reviewer.md must still ask whether the diff added behaviour "
        "the spec does not call for — the nothing-extra half of AC03"
    )
    assert "Scope creep is a divergence in the other direction" in normalized, (
        "the YAGNI direction must still be named explicitly as a "
        "divergence, not merely tolerated"
    )


@pytest.mark.covers("FR-01.05/AC04")
def test_spec_reviewer_still_checks_mockup_consistency():
    """FR-01.05 AC04: a UI section's built screen is read against its design
    mockup first, never ignored or loosely approximated. Pin the
    'Mockup-consistent?' question and its contradiction rule, both of which
    are what makes this a real check rather than an optional style note.
    """
    body = SPEC_REVIEWER.read_text(encoding="utf-8")
    normalized = " ".join(body.split())
    assert "**Mockup-consistent?**" in normalized, (
        "spec-reviewer.md must still ask whether the diff matches the "
        "mockup when a `## Design Reference` exists"
    )
    assert (
        "If the mockup and the section description **contradict each "
        "other**, REJECT" in normalized
    ), (
        "the mockup/description contradiction rule must still force a "
        "REJECT — a silent choice either way discards the reason mockups "
        "exist, per AC04's own wording"
    )

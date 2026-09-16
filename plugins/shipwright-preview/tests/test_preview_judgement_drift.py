"""Drift tests for FR-01.12's two judgement rows — campaign decision D7
(req3-06-enforcement-mono, sub-iterate e6).

The AC-evidence ledger (`.shipwright/planning/campaigns/2026-07-23-req3-ac-
evidence-ledger-mono.md`, FR-01.12 #2/#6) classifies both as
`prompt-only (judgement)`: whether missing settings were genuinely "walked
through" (AC03) rather than merely reported, and whether a start failure's
cause was actually "addressed" (AC07) rather than only stated, is behaviour
inside a conversation — no artifact a deterministic check can observe. D7
forbids a gate; the honest ceiling is a drift test pinning that SKILL.md
still instructs it.

A failure here means the governing instruction changed — update the
pinned text to match, never delete the test to make it pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "preview" / "SKILL.md"
)


@pytest.mark.covers("FR-01.12/AC03")
def test_missing_settings_walked_through_instruction_present():
    """FR-01.12 AC03: a missing setting is walked through with the user,
    never just reported and left. Pin the refusal-of-the-lazy-answer
    instruction and the walked-through obligation it pairs with.
    """
    normalized = " ".join(SKILL_PATH.read_text(encoding="utf-8").split())
    assert 'Do NOT just tell the user to "check logs"' in normalized, (
        "the refusal-of-the-lazy-answer instruction must survive verbatim "
        "— without it a validation failure could be reported and dropped"
    )
    assert "guide them through setting the values" in normalized, (
        "the walked-through obligation must survive verbatim — this is "
        "the only enforcement a judgement criterion can have (D7)"
    )


@pytest.mark.covers("FR-01.12/AC07")
def test_start_failure_cause_addressed_instruction_present():
    """FR-01.12 AC07: a start failure's cause is actively addressed, not
    merely reported to the user. Pin the addressed-not-just-reported
    instruction verbatim.
    """
    normalized = " ".join(SKILL_PATH.read_text(encoding="utf-8").split())
    assert "Do not just report the error — help resolve it." in normalized, (
        "the addressed-not-merely-reported instruction must survive "
        "verbatim — losing it silently drops AC07's guarantee"
    )

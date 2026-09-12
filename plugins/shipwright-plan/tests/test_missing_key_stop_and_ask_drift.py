"""Drift test for FR-01.03 #1's judgement half — campaign decision D7.

The AC-evidence ledger (`.shipwright/planning/campaigns/2026-07-23-req3-ac-
evidence-ledger-mono.md`, FR-01.03 #1) names one criterion with two directions:

1. A missing review key must make the session STOP and ask the user, rather
   than silently proceed. This is conversational behavior — there is no file
   artifact a deterministic check can observe mid-session, so it cannot be
   mechanically gated. D7 forbids building an LLM-judgment gate for it; the
   only legitimate enforcement is a drift test pinning the instruction.
2. A key that IS available must not be silently skipped. That direction IS
   mechanisable and is gated by `plan_gate_extras.review_key_honesty`
   (see `test_plan_gate_extras.py`).

This file covers direction 1 only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "plan" / "SKILL.md"
)


@pytest.mark.covers("FR-01.03/AC02")
def test_missing_review_key_stop_and_ask_instruction_present():
    body = SKILL_PATH.read_text(encoding="utf-8")
    assert "Branch B" in body and "missing_keys" in body, (
        "the missing_keys branch must still be named in SKILL.md — it is "
        "where the stop-and-ask instruction lives"
    )
    assert "STOP. Ask user verbatim" in body, (
        "the missing-key stop-and-ask instruction must survive verbatim — "
        "this is the only enforcement a judgement criterion can have (D7); "
        "losing the sentence silently removes the guarantee entirely"
    )
    assert "Do NOT proceed until chosen" in body, (
        "the 'do not proceed until chosen' clause must survive verbatim — "
        "without it the STOP is advisory rather than blocking"
    )

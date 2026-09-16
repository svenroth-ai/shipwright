"""Drift test for FR-01.08 #8's judgement half — campaign decision D7
(req3-06-enforcement-mono, sub-iterate e6).

The AC-evidence ledger (`.shipwright/planning/campaigns/2026-07-23-req3-ac-
evidence-ledger-mono.md`, FR-01.08 #8) names one criterion with two
directions:

1. An operator-requested rollback "confirms first" — a live
   `AskUserQuestion` with no artifact a deterministic check can observe
   afterward. No oracle exists, so D7 forbids a gate. Drift-tested here.
2. It then "proves alive" — mechanised by
   `deploy_checks.check_manual_rollback_proves_alive`
   (`test_verifiers_test_changelog_deploy.py`).

This file covers direction 1 only. A failure here means the governing
instruction changed — update the pinned text to match, never delete the
test to make it pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "deploy" / "SKILL.md"
)


@pytest.mark.covers("FR-01.08/AC12")
def test_manual_rollback_requires_explicit_confirmation_instruction_present():
    normalized = " ".join(SKILL_PATH.read_text(encoding="utf-8").split())
    assert "## Manual Rollback (`--rollback`)" in normalized, (
        "the Manual Rollback section must still exist — it is where the "
        "confirms-first instruction lives"
    )
    assert "Require explicit confirmation" in normalized, (
        "step 3's 'require explicit confirmation' instruction must survive "
        "verbatim — this is the only enforcement a judgement criterion can "
        "have (D7); losing the sentence silently removes the guarantee"
    )
    assert "this `AskUserQuestion` is the whole mechanism" in normalized, (
        "the self-documented reason this stays judgement, not enforced, "
        "must survive — no artifact records that the question was asked"
    )

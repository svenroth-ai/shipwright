"""Drift test for FR-01.09 #1's judgement half — campaign decision D7
(req3-06-enforcement-mono, sub-iterate e6).

The AC-evidence ledger (`.shipwright/planning/campaigns/2026-07-23-req3-ac-
evidence-ledger-mono.md`, FR-01.09 #1) names one criterion with three
parts: the release note (`enforced`), the version marking (`enforced,
tested` — `changelog_checks.check_git_tag_exists`), and opening the
release request (`prompt-only (judgement)`). Whether `gh pr create`
actually opened a request has no local-state artifact a deterministic
check can read without a live `gh`/network call, and it is best-effort,
conditional on being off-main — no oracle exists, so D7 forbids a gate.
This file covers the request-opening third only. A failure here means the
governing instruction changed — update the pinned text to match, never
delete the test to make it pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "changelog" / "SKILL.md"
)


@pytest.mark.covers("FR-01.09/AC01")
def test_create_pr_step_instruction_present():
    normalized = " ".join(SKILL_PATH.read_text(encoding="utf-8").split())
    assert "## Step 7: Create PR (Optional)" in normalized, (
        "the Create PR step must still exist — it is the only place the "
        "release request is opened"
    )
    assert "gh pr create" in normalized, (
        "the gh pr create invocation must survive verbatim — losing it "
        "silently drops the request-opening guarantee"
    )
    assert "Only if on a feature branch" in normalized, (
        "the off-main condition must survive — it is why this stays "
        "best-effort/conditional rather than an unconditional mechanism"
    )

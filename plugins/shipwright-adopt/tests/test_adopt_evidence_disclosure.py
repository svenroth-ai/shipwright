"""Onboarding says the committed evidence needs refreshing — twice.

iterate-2026-08-05-adopt-derived-evidence-rollout, AC-4 / AC-5.

Since #480 an iterate branch does not carry the derived compliance documents, so
after onboarding they stay at the adoption commit until a release or an on-demand
refresh moves them. That is the right design and an invisible one: nothing in the
handover said it, and the generated guidance said "Compliance + dashboard refresh"
with no hint that it meant the working tree only.

Two places, because they fail differently. The handover banner is read once and
scrolls away; the generated `CLAUDE.md` is what a session six months later loads.
Surface assertions only — substring-based, so unrelated edits elsewhere in either
document do not turn red.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

STEP_H = (
    PLUGIN_ROOT / "skills" / "adopt" / "references"
    / "step-h-validate-commit-handoff.md"
)
#: Read by PATH, never imported. An earlier draft did `from scripts.lib import
#: claude_md_renderer`, which passed alone and failed in the full root with
#: `cannot import name ... from 'scripts.lib'` resolved to the COMPLIANCE
#: plugin's package — whichever plugin's `scripts.lib` loads first wins the name
#: for the whole process (ADR-045). Nothing here needs the module: every claim
#: below is about the text of the template that ships.
RENDERER = PLUGIN_ROOT / "scripts" / "lib" / "claude_md_renderer.py"


@pytest.fixture(scope="module")
def step_h() -> str:
    return STEP_H.read_text(encoding="utf-8")


# --- AC-4: the handover states the cadence and both refresh paths -------------


@pytest.mark.covers("FR-01.13")
def test_handoff_names_both_ways_to_refresh_the_evidence(step_h: str) -> None:
    assert "/shipwright-compliance --refresh-pr" in step_h, (
        "the on-demand half is the only path available between releases"
    )
    assert "/shipwright-changelog" in step_h, (
        "the release path is the one most projects will actually hit first"
    )


@pytest.mark.covers("FR-01.13")
def test_handoff_says_the_evidence_does_not_stay_current(step_h: str) -> None:
    """Naming the commands is not enough if nothing says why you would run them.

    The negation is matched ADJACENT to the word it negates. An earlier draft
    asserted `"not" in lowered and "continuous" in lowered`, which could not
    fail: "not" is a substring of "Nothing" and "cannot", both present elsewhere
    in this file, so the test reduced to "the word continuous appears somewhere"
    — and an inverted banner reading "refreshed continuously" passed it
    (Stage-1 spec review, medium).
    """
    assert "Evidence:" in step_h, "the banner does not report evidence state at all"
    assert re.search(r"not\s+continuously", step_h, re.IGNORECASE), (
        "the banner must say the committed evidence is NOT refreshed continuously "
        "— otherwise the commands read as optional extras"
    )


# --- the stamp step is wired, and its three outcomes are distinguished --------


@pytest.mark.covers("FR-01.13")
def test_step_h_stamps_before_committing_and_verifies_after(step_h: str) -> None:
    """All three anchors, in order — the COMMIT is the one that matters.

    Asserting only stamp < verify leaves the "before committing" half unpinned:
    moving the stamp instruction after the commit step keeps that green, and
    putting it there is exactly the defect the placement exists to prevent
    (Stage-1 spec review, medium).
    """
    assert "--stamp-adopted" in step_h and "--verify-commit" in step_h
    # Anchored on the STEP HEADINGS, not on the first mention of each flag. Both
    # flags are also cross-referenced inside step 1a's status list (`--verify-commit`
    # is named there to explain why `no_base` skips it), so `index()` on the flag
    # finds prose rather than the step and the ordering claim becomes meaningless.
    stamp = step_h.index("**Stamp the seeded evidence")
    commit = step_h.index("build_adopt_commit_message")
    verify = step_h.index("**Verify the commit actually carries the stamp**")
    assert stamp < commit < verify, (
        f"stamp/commit/verify are out of order ({stamp}/{commit}/{verify}) — a "
        "stamp after the commit is written into a tree the commit already left "
        "behind, and a verify before it proves nothing about what shipped"
    )
    assert "--base" in step_h, (
        "the mode never resolves HEAD, so an unpassed base silently yields no_base"
    )


@pytest.mark.covers("FR-01.13")
def test_step_h_stages_after_stamping(step_h: str) -> None:
    """The stamp writes the WORKTREE; the commit records the INDEX.

    Nothing in this skill staged anything before this change, so the ordering was
    left to improvisation — harmless until a stamp entered the flow, at which
    point staging before it ships pre-stamp blobs (Stage-1 spec review, high).
    """
    assert '"add"' in step_h or "git add" in step_h, (
        "no staging is prescribed at all, so what reaches the commit is improvised"
    )
    assert step_h.index("--stamp-adopted") < step_h.index('"add"'), (
        "staging before the stamp puts the pre-stamp bytes in the adoption commit"
    )


@pytest.mark.covers("FR-01.13")
def test_step_h_distinguishes_no_base_from_partial(step_h: str) -> None:
    """The two non-ok outcomes need opposite handling, so both must be named.

    `no_base` continues the adoption and skips verification; `partial` must stop
    it. Collapsing them either blocks a legitimate empty-repo onboarding or ships
    a half-stamped evidence set.
    """
    assert "no_base" in step_h and "partial" in step_h
    assert "Do not commit" in step_h, (
        "a partial stamp that still commits is the failure the status exists for"
    )


# --- AC-5: the fact outlives the banner --------------------------------------


@pytest.mark.covers("FR-01.13")
def test_generated_claude_md_carries_the_same_statement() -> None:
    """Read off the renderer's template, not a rendered fixture.

    The template is the thing that ships into every adopted repository; a fixture
    would only prove one call site rendered it.
    """
    template = RENDERER.read_text(encoding="utf-8")
    assert "How current is the audit evidence?" in template
    assert "--refresh-pr" in template and "/shipwright-changelog" in template
    assert "Source-State:" in template, (
        "the reader needs to know the documents name the commit they describe"
    )
    # The CADENCE, not just the commands. Without this the test passes if the
    # generated guidance drops or inverts "not continuously" and simply lists two
    # commands, which reads as optional tooling rather than a standing caveat
    # (external code review, low). Same adjacency rule as the handover test.
    assert re.search(r"not\s+continuously", template, re.IGNORECASE), (
        "the generated guidance does not say the committed evidence is NOT "
        "refreshed continuously — the one fact that makes the commands matter"
    )

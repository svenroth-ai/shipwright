"""Drift-protection for the Mini-Plan Protocol persistence rule
(iterate-2026-08-09-compaction-state-audit).

Root cause: a `small`-complexity mini-plan existed only in conversation
("Inline in session only (no file)") — a mid-session compaction destroyed it
outright, with no disk artifact to resume from. The fix makes persistence
unconditional across every complexity tier that runs the protocol; only the
content *depth* (work breakdown, alternative approach) stays medium-only.

Anchored on the `## Mini-Plan Protocol` heading first, per the same
anchor-then-search pattern as `test_skill_step_6_rules_present.py` — survives
wording tweaks, fails when the rule disappears or a `small`-only exemption
reappears.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ITERATION_PLANNING_MD = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
    / "references" / "iteration-planning.md"
)


def _extract_mini_plan_protocol_body(text: str) -> str:
    pattern = re.compile(
        r"^## Mini-Plan Protocol.*?(?=\n## )",
        flags=re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(0) if match else ""


def test_mini_plan_protocol_heading_present() -> None:
    text = ITERATION_PLANNING_MD.read_text(encoding="utf-8")
    body = _extract_mini_plan_protocol_body(text)
    assert body, (
        "Could not extract '## Mini-Plan Protocol' body from iteration-planning.md. "
        "If the heading was renamed, update this test's probe regex."
    )


def test_no_small_tier_no_file_exemption_remains() -> None:
    """The regression this test exists to catch: reintroducing a
    small-complexity carve-out that skips persisting the file."""
    text = ITERATION_PLANNING_MD.read_text(encoding="utf-8")
    body = _extract_mini_plan_protocol_body(text)
    lowered = body.lower()
    assert "inline in session only" not in lowered, (
        "Mini-Plan Protocol still carries a 'inline in session only' "
        "exemption — this reintroduces the small-complexity state-loss gap "
        "closed by iterate-2026-08-09-compaction-state-audit."
    )
    assert not re.search(r"small.{0,40}\(no file\)", lowered), (
        "Mini-Plan Protocol still gates persistence on complexity=small — "
        "persistence must be unconditional across every tier that runs "
        "the protocol."
    )


def test_persistence_applies_at_every_tier() -> None:
    text = ITERATION_PLANNING_MD.read_text(encoding="utf-8")
    body = _extract_mini_plan_protocol_body(text)
    assert "every" in body.lower() and "complexity tier" in body.lower(), (
        "Mini-Plan Protocol's Persistence sub-section must state the file "
        "is saved at every complexity tier that runs the protocol."
    )
    assert "-miniplan.md" in body, (
        "Mini-Plan Protocol must still name the persisted filename pattern."
    )


def test_content_depth_gating_is_preserved() -> None:
    """Only the file's existence became unconditional — the deeper content
    items (work breakdown, alternative approach) stay medium-only."""
    text = ITERATION_PLANNING_MD.read_text(encoding="utf-8")
    body = _extract_mini_plan_protocol_body(text)
    assert body.count("(medium only)") >= 2, (
        "Mini-Plan Protocol's Content section should still gate 'Work "
        "breakdown' and 'Alternative approach' as (medium only) — only "
        "persistence changed for small, not content depth."
    )

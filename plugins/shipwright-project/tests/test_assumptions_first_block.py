"""Drift-protection for OS2 — spec-driven "assumptions-first" pre-phase block
in /shipwright-project.

Re-established by iterate-2026-05-29-sp3-os2-reintegration after Campaign B
(PRs #89-#102) split the project SKILL.md without carrying the inline OS2
patch that Spec/external-frameworks-integration.md §6.2 prescribed.

Pins three things:

1. `references/interview-protocol.md` carries an assumptions-first block:
   before clarifying questions the agent lists its inferred assumptions
   (web-app vs CLI, stack, persistence, auth model) and asks for correction.
2. The block carries an MIT attribution footer to addyosmani/agent-skills.
3. The project Kern SKILL.md Step 1 surfaces the assumptions-first behavior
   so it fires before the first clarifying question.

Mirrors the lenient-substring drift pattern from the shipwright-iterate
reference doc tests.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# tests/ -> plugin root (shipwright-project)
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = PLUGIN_ROOT / "skills" / "project" / "SKILL.md"
INTERVIEW_PROTOCOL = SKILL_MD.parent / "references" / "interview-protocol.md"

# Example assumption dimensions the block must prompt the agent to surface.
REQUIRED_DIMENSIONS = [
    "web-app",       # web-app vs CLI
    "cli",
    "persistence",   # persistence / storage / database
    "auth",          # auth model
]


def _protocol_text() -> str:
    return INTERVIEW_PROTOCOL.read_text(encoding="utf-8")


def _assumptions_block() -> str:
    """Body of the first heading containing 'assumption' until the next H2.

    Anchored on the heading so dimension checks probe the assumptions block
    itself — NOT incidental mentions elsewhere in the file (e.g. the
    pre-existing 'compatible CLI front-end' note would false-positive a
    whole-file 'cli' substring search).
    """
    pattern = re.compile(
        r"^#{2,3} [^\n]*assumption[^\n]*$.*?(?=\n#{1,2} |\Z)",
        flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(_protocol_text())
    return match.group(0) if match else ""


def _kern_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _step_1_kern_body() -> str:
    """Body of `## Step 1: Interview` until the next H2."""
    pattern = re.compile(r"^## Step 1: Interview.*?(?=\n## )", flags=re.MULTILINE | re.DOTALL)
    match = pattern.search(_kern_text())
    return match.group(0) if match else ""


# --- interview-protocol.md block --------------------------------------------


def test_interview_protocol_exists() -> None:
    assert INTERVIEW_PROTOCOL.is_file(), (
        f"interview-protocol.md missing at {INTERVIEW_PROTOCOL}"
    )


def test_assumptions_first_heading_present() -> None:
    headings = [
        line.strip().lower()
        for line in _protocol_text().splitlines()
        if line.lstrip().startswith("#")
    ]
    matches = [h for h in headings if "assumption" in h]
    assert matches, (
        "interview-protocol.md must carry an assumptions-first heading "
        f"(contains 'assumption'). Headings present: {headings}"
    )


def test_assumptions_listed_before_clarifying_questions() -> None:
    block = _assumptions_block().lower()
    assert block, (
        "Could not extract an assumptions block (heading containing "
        "'assumption') from interview-protocol.md."
    )
    assert "inferred assumptions" in block, (
        "The assumptions block must instruct the agent to list its 'inferred "
        "assumptions' explicitly."
    )
    assert "clarifying question" in block, (
        "The assumptions block must tie itself to clarifying questions (list "
        "assumptions BEFORE asking them)."
    )
    # The ordering word 'before' must appear in the assumptions context.
    assert "before" in block, (
        "The assumptions block must state assumptions come BEFORE clarifying "
        "questions."
    )


@pytest.mark.parametrize("dimension", REQUIRED_DIMENSIONS)
def test_assumptions_block_names_dimensions(dimension: str) -> None:
    block = _assumptions_block().lower()
    assert dimension in block, (
        f"Assumptions-first block must name the '{dimension}' assumption "
        "dimension (web-app vs CLI, stack, persistence, auth model). Checked "
        "inside the assumptions block, not the whole file."
    )


def test_assumptions_block_has_mit_attribution() -> None:
    lowered = _protocol_text().lower()
    assert (
        "addyosmani/agent-skills" in lowered
        and "addy osmani" in lowered
        and "mit" in lowered
    ), (
        "interview-protocol.md must carry an MIT attribution footer to "
        "addyosmani/agent-skills (© Addy Osmani) per Spec §7.2."
    )


# --- Kern surfacing ---------------------------------------------------------


def test_kern_step_1_surfaces_assumptions_first() -> None:
    body = _step_1_kern_body()
    assert body, "Could not extract `## Step 1: Interview` body from Kern SKILL.md."
    assert "assumption" in body.lower(), (
        "Project Kern SKILL.md Step 1 must surface the assumptions-first "
        "behavior so it fires before the first clarifying question. Add a "
        "pointer to interview-protocol.md's assumptions block."
    )

"""Drift-protection for SP3 — systematic-debugging sub-skill (F-debug.md)
and its BUG-intent routing in the iterate Kern.

Re-established by iterate-2026-05-29-sp3-os2-reintegration after Campaign B
(PRs #89-#102) split the iterate SKILL.md without carrying the inline SP3
patch that Spec/external-frameworks-integration.md §6.2 prescribed.

Pins four things:

1. `references/F-debug.md` exists, is non-empty, and carries the Superpowers
   Iron Law verbatim plus the 4-phase debugging structure.
2. F-debug.md carries an MIT attribution footer to obra/superpowers.
3. F-debug.md stays within the 400-LOC runtime-prompt budget.
4. The iterate Kern routes BUG intent through F-debug (link resolves) AND
   states the reviewer gate (reject a fix that patches a symptom, not the
   root cause). `references/path-c-bug.md` points at F-debug too.

Mirrors the drift-protection pattern in test_boundary_probes_doc.py and
test_skill_step_6_rules_present.py (anchored section extraction, lenient
substring matching that survives prose edits but fails on a dropped rule).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# tests/ -> plugin root (shipwright-iterate)
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = PLUGIN_ROOT / "skills" / "iterate" / "SKILL.md"
REFERENCES_DIR = SKILL_MD.parent / "references"
F_DEBUG = REFERENCES_DIR / "F-debug.md"
PATH_C_BUG = REFERENCES_DIR / "path-c-bug.md"

# The Iron Law must appear verbatim (Superpowers framing). Matched
# case-insensitively so a Title-Case rendering still passes.
IRON_LAW = "NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST"

# The 4 systematic-debugging phases. Short keywords so prose edits like
# "Phase 3 — Recent Changes (git bisect)" still match.
REQUIRED_PHASES = [
    "read error",
    "reproduce",
    "recent changes",
    "component-boundary",
]


def _f_debug_text() -> str:
    return F_DEBUG.read_text(encoding="utf-8")


def _f_debug_headings() -> list[str]:
    return [
        line.strip().lower()
        for line in _f_debug_text().splitlines()
        if line.lstrip().startswith("#")
    ]


def _kern_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _path_c_kern_body() -> str:
    """Body of `## Path C: BUG ...` until the next H2. Anchored on the
    heading so we probe the routing section, not arbitrary prose.
    """
    pattern = re.compile(r"^## Path C: BUG.*?(?=\n## )", flags=re.MULTILINE | re.DOTALL)
    match = pattern.search(_kern_text())
    return match.group(0) if match else ""


# --- F-debug.md content -----------------------------------------------------


def test_f_debug_exists() -> None:
    assert F_DEBUG.is_file(), (
        f"F-debug.md missing at {F_DEBUG}. SP3 (systematic-debugging) was "
        "never re-established after Campaign B — see "
        "Spec/external-frameworks-integration.md §SP3 + §6.2."
    )


def test_f_debug_not_empty() -> None:
    assert _f_debug_text().strip(), "F-debug.md is empty"


def test_f_debug_carries_iron_law() -> None:
    assert IRON_LAW.lower() in _f_debug_text().lower(), (
        f"F-debug.md must carry the Iron Law verbatim: {IRON_LAW!r}"
    )


@pytest.mark.parametrize("phase", REQUIRED_PHASES)
def test_f_debug_has_four_phases(phase: str) -> None:
    headings = _f_debug_headings()
    matches = [h for h in headings if phase in h]
    assert matches, (
        f"Required debugging phase '{phase}' not found in any F-debug.md "
        f"heading. Headings present: {headings}"
    )


def test_f_debug_has_four_distinct_phase_headings() -> None:
    """Sanity: the four phases are level-2/3 headings, not a prose run-on."""
    text = _f_debug_text()
    heading_count = sum(
        1 for line in text.splitlines() if line.lstrip().startswith("## ")
    )
    assert heading_count >= 4, (
        f"Expected at least 4 level-2 phase headings in F-debug.md, found "
        f"{heading_count}"
    )


def test_f_debug_has_mit_attribution() -> None:
    text = _f_debug_text().lower()
    assert "superpowers" in text and "jesse vincent" in text and "mit" in text, (
        "F-debug.md must carry an MIT attribution footer to obra/superpowers "
        "(© Jesse Vincent) per Spec §7.2 license discipline."
    )


def test_f_debug_under_loc_budget() -> None:
    loc = sum(1 for _ in _f_debug_text().splitlines())
    assert loc <= 400, (
        f"F-debug.md is {loc} LOC, must be <= 400 (runtime-prompt budget)."
    )


# --- Kern routing -----------------------------------------------------------


def test_kern_links_f_debug() -> None:
    """BUG intent must have an entry point into F-debug from the Kern."""
    assert "references/F-debug.md" in _kern_text(), (
        "Iterate Kern SKILL.md must link references/F-debug.md so BUG intent "
        "routes through systematic debugging."
    )


def test_path_c_routes_through_f_debug() -> None:
    """The Path C (BUG) section must route through F-debug AND state the
    root-cause reviewer gate.
    """
    body = _path_c_kern_body()
    assert body, "Could not extract `## Path C: BUG` body from Kern SKILL.md."
    assert "F-debug" in body, (
        "Path C must route BUG intent through F-debug before any fix."
    )
    lowered = body.lower()
    assert "root cause" in lowered and "symptom" in lowered, (
        "Path C must state the reviewer gate: reject a fix that patches a "
        "symptom rather than the root cause."
    )


def test_path_c_bug_reference_points_to_f_debug() -> None:
    assert PATH_C_BUG.is_file(), f"path-c-bug.md missing at {PATH_C_BUG}"
    assert "F-debug" in PATH_C_BUG.read_text(encoding="utf-8"), (
        "path-c-bug.md must point at F-debug as the 4-phase debugging protocol."
    )

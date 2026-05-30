"""Drift-protection test for references/confidence-anti-patterns.md.

Sub-Iterate B — Confidence Calibration Phase (campaign iterate-skill-hardening).

Asserts that the canonical sections appear as level-2 markdown headings
in the reference doc. Loose enough to allow prose edits, strict enough
to catch accidental section drops. Mirrors the drift-protection pattern
established in test_boundary_probes_doc.py (Sub-Iterate A).
"""

from pathlib import Path

import pytest

DOC_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "iterate"
    / "references"
    / "confidence-anti-patterns.md"
)

# Required section keywords. Match against case-insensitive substring of
# any heading line (## ... or ### ...). Keep keywords short so prose
# edits don't break the drift check.
REQUIRED_SECTIONS = [
    "are you confident",  # The "are you confident?" anti-pattern
    "asymptote",          # Asymptote heuristic (depth)
    "stop probing",       # Decision rule: when to stop probing
    "coverage",           # Coverage Stopping Rule (breadth) — completeness gate
    "untestable",         # The closed UNTESTABLE vocabulary
    "cross-references",   # Cross-references
]


def _load_headings() -> list[str]:
    text = DOC_PATH.read_text(encoding="utf-8")
    return [
        line.strip().lower()
        for line in text.splitlines()
        if line.lstrip().startswith("#")
    ]


def test_doc_exists():
    assert DOC_PATH.exists(), (
        f"confidence-anti-patterns.md missing at {DOC_PATH}"
    )


def test_doc_not_empty():
    assert DOC_PATH.read_text(encoding="utf-8").strip(), (
        "confidence-anti-patterns.md is empty"
    )


@pytest.mark.parametrize("keyword", REQUIRED_SECTIONS)
def test_required_section_present(keyword):
    headings = _load_headings()
    matches = [h for h in headings if keyword in h]
    assert matches, (
        f"Required section keyword '{keyword}' not found in any heading. "
        f"Headings present: {headings}"
    )


def test_at_least_four_level2_sections():
    """Sanity: at minimum 4 level-2 (## ) sections per spec scope."""
    text = DOC_PATH.read_text(encoding="utf-8")
    level2_count = sum(
        1 for line in text.splitlines() if line.startswith("## ")
    )
    assert level2_count >= 4, (
        f"Expected at least 4 level-2 sections, found {level2_count}"
    )


def test_links_to_boundary_probes():
    """Section 4 must link to boundary-probes.md (cross-reference rule)."""
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "boundary-probes.md" in text, (
        "confidence-anti-patterns.md must link to boundary-probes.md"
    )


def test_links_to_round_trip_tests():
    """Section 4 must link to round-trip-tests.md (cross-reference rule)."""
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "round-trip-tests.md" in text, (
        "confidence-anti-patterns.md must link to round-trip-tests.md"
    )

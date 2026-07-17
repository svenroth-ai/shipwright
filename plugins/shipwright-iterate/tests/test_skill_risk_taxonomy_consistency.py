"""Drift-protection: the literal `touches_io_boundary` must match between
the canonical taxonomy in `classify_complexity.py` and every consumer
in `SKILL.md`.

E spec MEDIUM-A2 — A's tests cover the producer side (key in
RISK_TAXONOMY) but not the consumer side. SKILL.md references the
literal in three load-bearing places (Risk Taxonomy table, Override
Classes, Phase Matrix + Path A Step 6a/7.5 prose). If the literal
drifts in any of them, the Boundary Probe gate silently goes dark.

Pattern mirrors the `_SHIPWRIGHT_FRAMEWORK_VARS` AST drift test
referenced in `.shipwright/agent_docs/conventions.md`.
"""
import pytest

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = PLUGIN_ROOT / "skills" / "iterate" / "SKILL.md"

# Add scripts/lib to path so we can import the taxonomy.
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from classify_complexity import RISK_TAXONOMY  # noqa: E402

LITERAL = "touches_io_boundary"
MIN_OCCURRENCES_IN_SKILL_MD = 3


@pytest.mark.covers("FR-01.11")
def test_literal_is_taxonomy_key():
    """Producer side: the literal is a key in RISK_TAXONOMY."""
    assert LITERAL in RISK_TAXONOMY


@pytest.mark.covers("FR-01.11")
def test_skill_md_exists():
    assert SKILL_PATH.exists(), f"SKILL.md missing at {SKILL_PATH}"


@pytest.mark.covers("FR-01.11")
def test_skill_md_contains_literal_at_least_three_times():
    """Consumer side: SKILL.md references the literal in at least 3 places.

    Currently observed in: Risk Taxonomy table, Override Classes,
    Phase Matrix row, Path A Step 6a / Step 7.5 / Path B / Path C
    cross-refs. Three is the floor; the test is not coupled to exact
    section names so prose moves don't break it.
    """
    text = SKILL_PATH.read_text(encoding="utf-8")
    count = text.count(LITERAL)
    assert count >= MIN_OCCURRENCES_IN_SKILL_MD, (
        f"SKILL.md must mention {LITERAL!r} at least "
        f"{MIN_OCCURRENCES_IN_SKILL_MD} times, found {count}. "
        f"If a section was removed deliberately, update this test floor."
    )


@pytest.mark.covers("FR-01.11")
def test_literal_present_in_risk_taxonomy_table():
    """Tighter check: the literal appears in the Risk Taxonomy section."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and "risk taxonomy" in line.lower():
            start = i
            break
    assert start is not None, "Risk Taxonomy section heading not found"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    section = "\n".join(lines[start:end])
    assert LITERAL in section, (
        f"Risk Taxonomy section missing {LITERAL!r} entry"
    )


@pytest.mark.covers("FR-01.11")
def test_literal_present_in_phase_matrix_section():
    """The literal appears in the Phase Matrix section (Section 6)."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and "phase matrix" in line.lower():
            start = i
            break
    assert start is not None, "Phase Matrix section heading not found"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    section = "\n".join(lines[start:end])
    assert LITERAL in section, (
        f"Phase Matrix section missing {LITERAL!r} reference"
    )


@pytest.mark.covers("FR-01.11")
def test_literal_present_in_override_classes_section():
    """The literal appears in the Override Classes section."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and "override classes" in line.lower():
            start = i
            break
    assert start is not None, "Override Classes section heading not found"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    section = "\n".join(lines[start:end])
    assert LITERAL in section, (
        f"Override Classes section missing {LITERAL!r} reference"
    )

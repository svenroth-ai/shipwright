"""Drift-protection: the `cross_component` risk flag + its integration-coverage
gate must be advertised in the runtime prose (iterate-2026-06-12-cross-component-gate).
The agent only executes what the prose says, so the prose IS the contract.
"""

from __future__ import annotations

from pathlib import Path

_IT = Path(__file__).resolve().parent.parent / "skills" / "iterate"
_SKILL = (_IT / "SKILL.md").read_text(encoding="utf-8")
_CAP = (_IT / "references" / "confidence-anti-patterns.md").read_text(encoding="utf-8")
_F5 = (_IT / "references" / "F5.md").read_text(encoding="utf-8")


def test_risk_taxonomy_row_present():
    assert "`cross_component`" in _SKILL
    rows = [ln for ln in _SKILL.splitlines() if ln.startswith("| `cross_component`")]
    assert rows, "no cross_component risk-taxonomy row in SKILL.md"
    row = rows[0]
    assert "integration coverage" in row.lower()
    assert "medium" in row  # min complexity
    assert "check_integration_coverage" in row  # the non-dodgeable verifier


def test_phase_matrix_integration_coverage_row():
    rows = [ln for ln in _SKILL.splitlines() if ln.startswith("| Integration Coverage")]
    assert rows, "no Integration Coverage row in the Phase Matrix"
    # trivial/small skip, medium/large gated on cross_component
    assert "`cross_component`" in rows[0]


def test_confidence_anti_patterns_has_integration_stopping_rule():
    low = _CAP.lower()
    assert "integration stopping rule" in low
    assert "cross_component" in _CAP
    assert "compose" in low
    # the three axes are named
    assert "depth" in low and "breadth" in low and "composition" in low


def test_f5_documents_integration_category():
    assert 'category' in _F5 and 'integration' in _F5
    assert "check_integration_coverage" in _F5


def test_step_7_5_advertises_integration_composition():
    # The spec AC requires Step 7.5 (Confidence Calibration) to advertise the gate.
    section = _SKILL[_SKILL.index("### Step 7.5"):]
    section = section[:section.index("\n### ")] if "\n### " in section else section
    low = section.lower()
    assert "integration composition" in low or "integration coverage" in low
    assert "cross_component" in section
    assert 'category:"integration"' in section or "category: \"integration\"" in section
    assert "check_integration_coverage" in section

"""Pins the load-bearing prose of the screenshot check (campaign B3c): an unattended agent reads it as the rule."""

import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
import png_compare  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "test"
REF = (SKILL_DIR / "references" / "step-3.7b-screenshot-check.md").read_text(encoding="utf-8")
SKILL = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

pytestmark = pytest.mark.covers("FR-01.06")


def test_documented_metric_and_tolerance_are_the_ones_in_code():
    assert png_compare.METRIC in REF
    assert f"<= **{png_compare.TOLERANCE}**" in REF
    assert f'"tolerance": {png_compare.TOLERANCE}' in REF
    assert f"{png_compare.GRID_W}x{png_compare.GRID_H}" in REF
    assert f"{png_compare.CELL_DELTA:.2f}" in REF


def test_every_outcome_has_a_stop_or_continue_instruction():
    rows = [line for line in REF.splitlines() if line.startswith(("| 0 ", "| 1 ", "| 2 "))]
    assert len(rows) == 4, rows
    for line in rows:
        action = line.rstrip(" |").rsplit("|", 1)[1]
        assert ("continue" in action) if line.startswith("| 0 ") else ("**STOP" in action), line
    assert "An error is NOT a pass" in REF


def test_nothing_may_be_waived_edited_or_approved():
    never = REF[REF.index("Never:"):]
    for forbidden in ("raise the tolerance", "edit or regenerate an approved design screen", "approve anything"):
        assert forbidden in never
    assert "not** a\ndesign-approval gate" in REF or "not** a design-approval gate" in REF.replace("\n", " ")


def test_only_brief_package_projects_are_blocked():
    assert "brief-package-applied.json" in REF and "brief-package-applied.json" in SKILL
    assert '"applies": false' in REF
    assert "keeps Step 3.7's non-blocking behaviour" in SKILL.replace("\n", " ")


def test_existing_fidelity_step_stays_non_blocking():
    old = (SKILL_DIR / "references" / "step-3.7-design-fidelity.md").read_text(encoding="utf-8")
    assert "Non-blocking (WARNING level)" in old
    assert "screenshot" not in old.lower()

"""Tests for check-sections.py script."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "checks" / "check-sections.py")


def run_check(args: list[str]) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_check_all_sections_written(planning_with_sections):
    output = run_check(["--planning-dir", str(planning_with_sections)])
    assert output["success"] is True
    assert output["missing"] == []
    assert len(output["written"]) == 3


def test_check_missing_sections(planning_with_plan):
    output = run_check(["--planning-dir", str(planning_with_plan)])
    assert output["success"] is False
    assert len(output["missing"]) == 3


def test_check_partial_sections(planning_with_plan):
    sections = planning_with_plan / "sections"
    sections.mkdir(exist_ok=True)
    (sections / "01-auth.md").write_text("# Section\n")

    output = run_check(["--planning-dir", str(planning_with_plan)])
    assert output["success"] is False
    assert output["missing"] == ["02-api", "03-frontend"]
    assert output["written"] == ["01-auth"]

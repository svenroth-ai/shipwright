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


# ---------------------------------------------------------------------------
# Dependency order — the promise "the numbering is the build order", checked
# ---------------------------------------------------------------------------


def _planning_with(tmp_path, manifest_body: str, names: list[str]):
    planning = tmp_path / "01-split"
    (planning / "sections").mkdir(parents=True)
    (planning / "plan.md").write_text(
        f"<!-- SECTION_MANIFEST\n{manifest_body}\nEND_MANIFEST -->\n", encoding="utf-8"
    )
    for name in names:
        (planning / "sections" / f"{name}.md").write_text("# Section\n", encoding="utf-8")
    return planning


def test_dependencies_are_reported(tmp_path):
    planning = _planning_with(tmp_path, "01-auth\n02-api: 01-auth", ["01-auth", "02-api"])
    output = run_check(["--planning-dir", str(planning)])
    assert output["success"] is True
    assert output["dependencies"] == {"01-auth": [], "02-api": ["01-auth"]}
    assert output["order_errors"] == []


def test_prerequisite_after_its_user_fails_the_gate(tmp_path):
    planning = _planning_with(tmp_path, "01-api: 02-db\n02-db", ["01-api", "02-db"])
    output = run_check(["--planning-dir", str(planning)])
    assert output["success"] is False
    assert output["missing"] == []          # every file exists …
    assert output["order_errors"]           # … the ORDER is what fails
    assert "numbered after it" in output["order_errors"][0]


def test_bare_manifest_declares_nothing_and_passes(tmp_path):
    """A plan written before dependencies were expressible is not stranded."""
    planning = _planning_with(tmp_path, "03-api\n01-auth\n02-db", ["01-auth", "02-db", "03-api"])
    output = run_check(["--planning-dir", str(planning)])
    assert output["success"] is True
    assert output["order_errors"] == []

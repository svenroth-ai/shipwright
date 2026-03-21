"""Tests for setup_implementation_session.py."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "checks" / "setup_implementation_session.py")


def run_setup(args: list[str]) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_setup_new_session(sample_section):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--file", str(sample_section),
        "--plugin-root", plugin_root,
        "--session-id", "build-test-1",
    ])

    assert output["success"] is True
    assert output["section_name"] == "01-auth"
    assert output["branch_name"] == "shipwright/01-auth"
    assert output["session_id"] == "build-test-1"


def test_setup_invalid_file(tmp_path):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--file", str(tmp_path / "nonexistent.md"),
        "--plugin-root", plugin_root,
    ])

    assert output["success"] is False
    assert "not found" in output["error"]


def test_setup_invalid_section_name(tmp_path):
    bad_file = tmp_path / "not-a-section.md"
    bad_file.write_text("# Not a section\n")
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--file", str(bad_file),
        "--plugin-root", plugin_root,
    ])

    assert output["success"] is False
    assert "Cannot extract section name" in output["error"]


def test_setup_loads_config(sample_section):
    # Create config in project root (detected via .git)
    project_root = sample_section.parent.parent.parent  # my-project/
    (project_root / ".git").mkdir(exist_ok=True)  # Mark as git root
    import json as json_mod
    (project_root / "shipwright_build_config.json").write_text(
        json_mod.dumps({"auto_push": True}), encoding="utf-8"
    )

    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--file", str(sample_section),
        "--plugin-root", plugin_root,
    ])

    assert output["success"] is True
    assert output["config"]["auto_push"] is True

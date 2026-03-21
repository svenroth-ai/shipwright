"""Tests for setup-planning-session.py script."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "checks" / "setup-planning-session.py")


def run_setup(args: list[str]) -> dict:
    """Run setup script and parse JSON output."""
    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_setup_new_session(sample_spec):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--file", str(sample_spec),
        "--plugin-root", plugin_root,
        "--session-id", "plan-test-123",
    ])
    assert output["success"] is True
    assert output["mode"] == "new"
    assert output["resume_from_step"] == 1


def test_setup_resume_session(sample_spec):
    plugin_root = str(Path(__file__).resolve().parent.parent)

    # First run
    run_setup(["--file", str(sample_spec), "--plugin-root", plugin_root])

    # Second run
    output = run_setup(["--file", str(sample_spec), "--plugin-root", plugin_root])
    assert output["success"] is True
    assert output["mode"] == "resume"


def test_setup_invalid_file(tmp_path):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--file", str(tmp_path / "nonexistent.md"),
        "--plugin-root", plugin_root,
    ])
    assert output["success"] is False
    assert "not found" in output["error"]


def test_setup_creates_sections_dir(sample_spec):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    run_setup(["--file", str(sample_spec), "--plugin-root", plugin_root])
    assert (sample_spec.parent / "sections").is_dir()

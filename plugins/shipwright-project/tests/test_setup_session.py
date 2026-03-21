"""Tests for setup-session.py script."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "checks" / "setup-session.py")


def run_setup(args: list[str], cwd: str = None) -> dict:
    """Run setup-session.py and parse JSON output."""
    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


# --- File mode tests ---

def test_setup_new_session_file_mode(sample_requirements):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--file", str(sample_requirements),
        "--plugin-root", plugin_root,
        "--session-id", "test-session-123",
    ])

    assert output["success"] is True
    assert output["mode"] == "new"
    assert output["input_mode"] == "file"
    assert output["resume_from_step"] == 1
    assert output["session_id"] == "test-session-123"
    assert output["initial_file"] is not None


def test_setup_resume_session(sample_requirements):
    plugin_root = str(Path(__file__).resolve().parent.parent)

    # First run
    run_setup([
        "--file", str(sample_requirements),
        "--plugin-root", plugin_root,
        "--session-id", "test-session-456",
    ])

    # Second run — should resume
    output = run_setup([
        "--file", str(sample_requirements),
        "--plugin-root", plugin_root,
        "--session-id", "test-session-456",
    ])

    assert output["success"] is True
    assert output["mode"] == "resume"


def test_setup_invalid_file(tmp_path):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--file", str(tmp_path / "nonexistent.md"),
        "--plugin-root", plugin_root,
        "--session-id", "test",
    ])

    assert output["success"] is False
    assert "not found" in output["error"]


def test_setup_empty_file(tmp_path):
    empty_file = tmp_path / "empty.md"
    empty_file.write_text("")
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--file", str(empty_file),
        "--plugin-root", plugin_root,
        "--session-id", "test",
    ])

    assert output["success"] is False
    assert "empty" in output["error"]


# --- Chat mode tests ---

def test_setup_chat_mode(tmp_path):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    planning = tmp_path / "my-project" / "planning"

    output = run_setup([
        "--planning-dir", str(planning),
        "--plugin-root", plugin_root,
        "--input-mode", "chat",
        "--session-id", "chat-test-1",
    ])

    assert output["success"] is True
    assert output["mode"] == "new"
    assert output["input_mode"] == "chat"
    assert output["initial_file"] is None
    assert planning.is_dir()


def test_setup_inline_mode(tmp_path):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    planning = tmp_path / "time-tracker" / "planning"

    output = run_setup([
        "--planning-dir", str(planning),
        "--plugin-root", plugin_root,
        "--input-mode", "inline",
        "--session-id", "inline-test-1",
    ])

    assert output["success"] is True
    assert output["input_mode"] == "inline"
    assert output["initial_file"] is None


def test_setup_chat_mode_resume(tmp_path):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    planning = tmp_path / "project" / "planning"

    # First run
    run_setup([
        "--planning-dir", str(planning),
        "--plugin-root", plugin_root,
        "--input-mode", "chat",
    ])

    # Second run — should resume
    output = run_setup([
        "--planning-dir", str(planning),
        "--plugin-root", plugin_root,
        "--input-mode", "chat",
    ])

    assert output["success"] is True
    assert output["mode"] == "resume"


def test_setup_no_file_no_dir():
    """Neither --file nor --planning-dir → error."""
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--plugin-root", plugin_root,
        "--input-mode", "chat",
    ])

    assert output["success"] is False
    assert "required" in output["error"].lower()


def test_setup_force_overwrites(tmp_path):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    planning = tmp_path / "project" / "planning"

    # First run
    run_setup([
        "--planning-dir", str(planning),
        "--plugin-root", plugin_root,
        "--input-mode", "chat",
    ])

    # Force overwrite
    output = run_setup([
        "--planning-dir", str(planning),
        "--plugin-root", plugin_root,
        "--input-mode", "chat",
        "--force",
    ])

    assert output["success"] is True
    assert output["mode"] == "new"

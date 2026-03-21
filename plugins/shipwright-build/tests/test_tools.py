"""Tests for shipwright-build tools."""

import json
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "tools"


def run_tool(script_name: str, args: list[str]) -> dict:
    script = str(TOOLS_DIR / script_name)
    result = subprocess.run(
        [sys.executable, script] + args,
        capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_update_section_state(tmp_path):
    output = run_tool("update_section_state.py", [
        "--section", "01-auth",
        "--status", "complete",
        "--commit", "abc123",
        "--project-root", str(tmp_path),
    ])

    assert output["success"] is True
    assert output["section"] == "01-auth"

    # Verify file was written
    config = json.loads((tmp_path / "shipwright_build_config.json").read_text(encoding="utf-8"))
    assert config["sections"][0]["name"] == "01-auth"
    assert config["sections"][0]["status"] == "complete"
    assert config["sections"][0]["commit"] == "abc123"


def test_update_section_state_existing(tmp_path):
    # Create initial config
    (tmp_path / "shipwright_build_config.json").write_text(
        json.dumps({"sections": [{"name": "01-auth", "status": "in_progress"}]}),
        encoding="utf-8",
    )

    output = run_tool("update_section_state.py", [
        "--section", "01-auth",
        "--status", "complete",
        "--commit", "def456",
        "--project-root", str(tmp_path),
    ])

    assert output["success"] is True
    config = json.loads((tmp_path / "shipwright_build_config.json").read_text(encoding="utf-8"))
    assert config["sections"][0]["status"] == "complete"


def test_write_decision_log(tmp_path):
    (tmp_path / "agent_docs").mkdir()

    decisions = json.dumps([
        {"decision": "Use Zustand", "reason": "Simpler than Redux", "category": "architecture"},
        {"decision": "Magic link auth", "reason": "Better UX", "category": "design"},
    ])

    output = run_tool("write_decision_log.py", [
        "--project-root", str(tmp_path),
        "--section", "01-auth",
        "--decisions", decisions,
    ])

    assert output["success"] is True
    assert output["entries_written"] == 2

    log = (tmp_path / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")
    assert "Use Zustand" in log
    assert "Magic link auth" in log
    assert "architecture" in log


def test_write_decision_log_creates_dir(tmp_path):
    """agent_docs/ doesn't exist yet — should be created."""
    decisions = json.dumps([{"decision": "Test", "reason": "Because", "category": "test"}])

    output = run_tool("write_decision_log.py", [
        "--project-root", str(tmp_path),
        "--section", "01-test",
        "--decisions", decisions,
    ])

    assert output["success"] is True
    assert (tmp_path / "agent_docs" / "decision_log.md").exists()


def test_generate_session_handoff(tmp_path):
    (tmp_path / "agent_docs").mkdir()

    # Need to be in a git repo for handoff to work
    subprocess.run(["git", "init", "-b", "main"], cwd=str(tmp_path),
                    capture_output=True, encoding="utf-8")

    output = run_tool("generate_session_handoff.py", [
        "--project-root", str(tmp_path),
        "--section", "01-auth",
        "--status", "in_progress",
    ])

    assert output["success"] is True
    handoff = (tmp_path / "agent_docs" / "session_handoff.md").read_text(encoding="utf-8")
    assert "01-auth" in handoff
    assert "in_progress" in handoff

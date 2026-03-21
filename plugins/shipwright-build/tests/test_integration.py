"""Integration tests for shipwright-build."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def run_script(subdir: str, script_name: str, args: list[str]) -> dict:
    script = str(SCRIPTS_DIR / subdir / script_name)
    result = subprocess.run(
        [sys.executable, script] + args,
        capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


@pytest.mark.integration
def test_setup_and_track_section(tmp_path):
    """Test setup → implement → track flow."""
    # Create project structure
    project = tmp_path / "project"
    project.mkdir()
    (project / "agent_docs").mkdir()
    sections = project / "planning" / "sections"
    sections.mkdir(parents=True)

    section = sections / "01-auth.md"
    section.write_text("# Section: 01-auth\n\n## Overview\nAuth implementation.\n")

    # Init git repo
    subprocess.run(["git", "init", "-b", "main"], cwd=str(project),
                    capture_output=True, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(project),
                    capture_output=True, encoding="utf-8")
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(project),
                    capture_output=True, encoding="utf-8")

    plugin_root = str(Path(__file__).resolve().parent.parent)

    # 1. Setup
    setup_result = run_script("checks", "setup_implementation_session.py", [
        "--file", str(section),
        "--plugin-root", plugin_root,
        "--session-id", "int-test-1",
    ])
    assert setup_result["success"] is True
    assert setup_result["section_name"] == "01-auth"

    # 2. Update section state
    state_result = run_script("tools", "update_section_state.py", [
        "--section", "01-auth",
        "--status", "complete",
        "--commit", "abc123",
        "--project-root", str(project),
    ])
    assert state_result["success"] is True

    # 3. Write decision log
    decisions = json.dumps([
        {"decision": "Use Supabase magic link", "reason": "Better UX", "category": "design"},
    ])
    log_result = run_script("tools", "write_decision_log.py", [
        "--project-root", str(project),
        "--section", "01-auth",
        "--decisions", decisions,
    ])
    assert log_result["success"] is True

    # 4. Generate handoff
    handoff_result = run_script("tools", "generate_session_handoff.py", [
        "--project-root", str(project),
        "--section", "01-auth",
        "--status", "complete",
    ])
    assert handoff_result["success"] is True

    # 5. Verify artifacts
    assert (project / "shipwright_build_config.json").exists()
    assert (project / "agent_docs" / "decision_log.md").exists()
    assert (project / "agent_docs" / "session_handoff.md").exists()

    # Verify config content
    config = json.loads((project / "shipwright_build_config.json").read_text(encoding="utf-8"))
    assert config["sections"][0]["status"] == "complete"
    assert config["sections"][0]["commit"] == "abc123"

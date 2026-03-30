"""Tests for shipwright-build tools."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "tools"
_SHARED_DECISION_LOG = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "shared" / "scripts" / "tools" / "write_decision_log.py"
)
_spec = importlib.util.spec_from_file_location("write_decision_log", _SHARED_DECISION_LOG)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
append_decision = _mod.append_decision


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


def test_update_section_state_with_test_results(tmp_path):
    output = run_tool("update_section_state.py", [
        "--section", "01-auth",
        "--status", "complete",
        "--commit", "abc123",
        "--tests-passed", "26",
        "--tests-total", "26",
        "--review-findings", json.dumps([
            {"finding": "Missing input validation", "status": "fixed"},
        ]),
        "--project-root", str(tmp_path),
    ])

    assert output["success"] is True
    config = json.loads((tmp_path / "shipwright_build_config.json").read_text(encoding="utf-8"))
    section = config["sections"][0]
    assert section["tests_passed"] == 26
    assert section["tests_total"] == 26
    assert len(section["code_review_findings"]) == 1
    assert section["code_review_findings"][0]["status"] == "fixed"


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

    n1 = append_decision(
        tmp_path,
        section_ref="Build — 01-auth",
        commit_hash="abc123",
        context="Simpler than Redux",
        decision="Use Zustand",
        consequences="Less boilerplate",
        rejected="Redux, React Context",
    )
    n2 = append_decision(
        tmp_path,
        section_ref="Build — 01-auth",
        commit_hash="abc123",
        context="Better UX",
        decision="Magic link auth",
        consequences="No password management",
        rejected="Password auth",
    )

    assert n1 == 1
    assert n2 == 2

    log = (tmp_path / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")
    assert "ADR-001" in log
    assert "ADR-002" in log
    assert "Use Zustand" in log
    assert "Magic link auth" in log


def test_write_decision_log_creates_dir(tmp_path):
    """agent_docs/ doesn't exist yet — should be created."""
    n = append_decision(
        tmp_path,
        section_ref="Build — 01-test",
        commit_hash="n/a",
        context="Testing",
        decision="Test decision",
        consequences="None",
    )

    assert n == 1
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

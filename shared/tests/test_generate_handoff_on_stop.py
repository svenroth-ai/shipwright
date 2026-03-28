"""Tests for the Stop hook that generates session_handoff.md."""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# The hook script path
HOOK_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "generate_handoff_on_stop.py"


def run_hook(cwd: Path, env_extra: dict | None = None, stdin_data: str = "{}") -> subprocess.CompletedProcess:
    """Run the hook as a subprocess, mimicking Claude Code invocation."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=stdin_data,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


def test_exits_zero_when_not_shipwright_project(tmp_path):
    """Hook silently exits 0 when no config or agent_docs exist."""
    result = run_hook(tmp_path)
    assert result.returncode == 0
    # No output expected — guard clause skips generation
    assert "hookSpecificOutput" not in result.stdout or "skipped" in result.stdout.lower()


def test_generates_handoff_with_run_config(tmp_project):
    """Hook generates session_handoff.md when shipwright_run_config.json exists."""
    config = {"scope": "full_app", "profile": "test"}
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )

    result = run_hook(
        tmp_project,
        env_extra={"SHIPWRIGHT_SESSION_ID": "test-session-42"},
    )

    assert result.returncode == 0
    handoff = tmp_project / "agent_docs" / "session_handoff.md"
    assert handoff.exists()
    content = handoff.read_text(encoding="utf-8")
    assert "# Session Handoff" in content
    assert "test-session-42" in content
    assert "session end" in content


def test_generates_handoff_with_only_agent_docs(tmp_project):
    """Hook generates handoff when only agent_docs/ exists (early phase)."""
    result = run_hook(tmp_project)

    assert result.returncode == 0
    handoff = tmp_project / "agent_docs" / "session_handoff.md"
    assert handoff.exists()
    content = handoff.read_text(encoding="utf-8")
    assert "# Session Handoff" in content
    assert "not_started" in content


def test_outputs_valid_json_with_hook_context(tmp_project):
    """Hook outputs valid JSON with hookSpecificOutput."""
    result = run_hook(tmp_project)

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "hookSpecificOutput" in output
    assert output["hookSpecificOutput"]["hookEventName"] == "Stop"
    assert "session_handoff.md" in output["hookSpecificOutput"]["additionalContext"]


def test_idempotent(tmp_project):
    """Running the hook twice produces valid results both times."""
    result1 = run_hook(tmp_project)
    assert result1.returncode == 0

    result2 = run_hook(tmp_project)
    assert result2.returncode == 0

    handoff = tmp_project / "agent_docs" / "session_handoff.md"
    assert handoff.exists()
    content = handoff.read_text(encoding="utf-8")
    assert "# Session Handoff" in content


def test_default_session_id_when_env_not_set(tmp_project):
    """Hook uses 'unknown' when SHIPWRIGHT_SESSION_ID is not set."""
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_SESSION_ID", None)

    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input="{}",
        capture_output=True,
        text=True,
        cwd=tmp_project,
        env=env,
    )

    assert result.returncode == 0
    handoff = tmp_project / "agent_docs" / "session_handoff.md"
    assert handoff.exists()
    assert "unknown" in handoff.read_text(encoding="utf-8")


def test_handles_malformed_stdin(tmp_project):
    """Hook handles malformed stdin gracefully."""
    result = run_hook(tmp_project, stdin_data="not valid json{{{")
    assert result.returncode == 0


def test_with_full_config_set(project_with_configs):
    """Hook generates comprehensive handoff with all configs present."""
    result = run_hook(
        project_with_configs,
        env_extra={"SHIPWRIGHT_SESSION_ID": "full-session"},
    )

    assert result.returncode == 0
    handoff = project_with_configs / "agent_docs" / "session_handoff.md"
    content = handoff.read_text(encoding="utf-8")
    assert "full-session" in content
    assert "build" in content  # Phase should be detected as build
    assert "shipwright_run_config.json" in content

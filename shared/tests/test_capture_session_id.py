"""Tests for the canonical shared/scripts/hooks/capture_session_id.py.

This hook replaces the 8 per-plugin duplicates that used to live in
plugins/*/scripts/hooks/. All plugin hooks.json files reference this
single script now.
"""

import json
import subprocess
import sys
from pathlib import Path

CAPTURE_SCRIPT = str(
    Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "capture_session_id.py"
)


def _run(payload: str, **env) -> subprocess.CompletedProcess:
    """Run the hook with the given stdin payload and env overrides."""
    import os
    merged_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, CAPTURE_SCRIPT],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=merged_env,
    )


def test_outputs_session_id_and_plugin_root(monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/plugin/root")

    result = _run(json.dumps({"session_id": "test-session-abc"}))

    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]

    assert "SHIPWRIGHT_SESSION_ID=test-session-abc" in context
    assert "SHIPWRIGHT_PLUGIN_ROOT=/fake/plugin/root" in context
    # No upstream references — confirms we're not pulling in deep-project vars
    assert "DEEP_" not in context


def test_outputs_project_root(monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/plugin/root")

    result = _run(json.dumps({"session_id": "test-session-abc"}))
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]

    assert "SHIPWRIGHT_PROJECT_ROOT=" in context


def test_emits_loop_vars_when_set(monkeypatch):
    """Loop env vars (ROOT_SESSION_ID, LOOP_ID, LOOP_UNIT_ID) must propagate."""
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")
    monkeypatch.setenv("SHIPWRIGHT_ROOT_SESSION_ID", "root-sess-123")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-abc")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "01-models")

    result = _run(json.dumps({"session_id": "sess-xyz"}))
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]

    assert "SHIPWRIGHT_ROOT_SESSION_ID=root-sess-123" in context
    assert "SHIPWRIGHT_LOOP_ID=loop-abc" in context
    assert "SHIPWRIGHT_LOOP_UNIT_ID=01-models" in context


def test_omits_loop_vars_when_unset(monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_ROOT_SESSION_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_LOOP_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_LOOP_UNIT_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")

    result = _run(json.dumps({"session_id": "sess-xyz"}))
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]

    assert "SHIPWRIGHT_ROOT_SESSION_ID" not in context
    assert "SHIPWRIGHT_LOOP_ID" not in context
    assert "SHIPWRIGHT_LOOP_UNIT_ID" not in context


def test_no_session_id_no_output():
    """Empty payload → no output."""
    result = _run("{}")
    assert result.stdout.strip() == ""


def test_invalid_json_no_crash():
    """Invalid JSON → exit 0, no output (hooks must never fail)."""
    result = _run("not json")
    assert result.returncode == 0


def test_existing_matching_session_id_omits_reassignment(monkeypatch):
    """If SHIPWRIGHT_SESSION_ID already matches, do not re-emit it (noise)."""
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "already-set")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")

    result = _run(json.dumps({"session_id": "already-set"}))
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]

    assert "SHIPWRIGHT_SESSION_ID" not in context
    # Other context still emitted
    assert "SHIPWRIGHT_PLUGIN_ROOT=/fake/root" in context


def test_claude_env_file_receives_session_id(monkeypatch, tmp_path):
    """SHIPWRIGHT_SESSION_ID must be appended to CLAUDE_ENV_FILE so
    bash subprocesses inherit it (additionalContext alone does not)."""
    env_file = tmp_path / "env.sh"
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))

    _run(json.dumps({"session_id": "env-test-id"}))

    content = env_file.read_text(encoding="utf-8")
    assert "export SHIPWRIGHT_SESSION_ID=env-test-id" in content


def test_claude_env_file_idempotent(monkeypatch, tmp_path):
    """Re-running the hook with the same session id must not duplicate the export."""
    env_file = tmp_path / "env.sh"
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))

    _run(json.dumps({"session_id": "same-id"}))
    _run(json.dumps({"session_id": "same-id"}))

    content = env_file.read_text(encoding="utf-8")
    assert content.count("SHIPWRIGHT_SESSION_ID=same-id") == 1


def test_resolve_project_root_via_subdirectory(monkeypatch, tmp_path):
    """When cwd has no marker but exactly one child does, project root
    should resolve to that child (monorepo subdirectory support)."""
    child = tmp_path / "app"
    child.mkdir()
    (child / "shipwright_run_config.json").write_text("{}", encoding="utf-8")

    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")
    monkeypatch.chdir(tmp_path)

    result = _run(json.dumps({"session_id": "root-resolve-test"}))
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]

    project_root_line = [
        line for line in context.split("\n") if line.startswith("SHIPWRIGHT_PROJECT_ROOT=")
    ][0]
    assert str(child) in project_root_line

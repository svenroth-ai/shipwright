"""Tests for capture_session_id.py's CLAUDE_ENV_FILE propagation.

Split out of test_capture_session_id.py (bloat gate) — this group covers one
cohesive behavior: making a hook-observed env var reach a Bash-tool
subprocess's real OS environment, which additionalContext (text shown to the
model) cannot do. See that script's own docstring and
docs/hooks-and-pipeline.md's capture_session_id.py section.
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


def test_claude_env_file_receives_loop_unit_id(monkeypatch, tmp_path):
    """SHIPWRIGHT_LOOP_UNIT_ID must also reach CLAUDE_ENV_FILE (trg-33d30377):
    a campaign runner's authorship guard reads it via os.environ, which
    additionalContext (text shown to the model, not an OS var) never fills."""
    env_file = tmp_path / "env.sh"
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "p3.8")

    _run(json.dumps({"session_id": "loop-env-test-id"}))

    content = env_file.read_text(encoding="utf-8")
    assert "export SHIPWRIGHT_SESSION_ID=loop-env-test-id" in content
    assert "export SHIPWRIGHT_LOOP_UNIT_ID=p3.8" in content


def test_claude_env_file_quotes_shell_metacharacters(monkeypatch, tmp_path):
    """A value containing shell metacharacters must be quoted, not written
    raw — CLAUDE_ENV_FILE is sourced by a shell, so an unquoted value with
    `$()`, backticks, `;` or a quote could inject arbitrary shell content
    (flagged in code review of trg-33d30377's SHIPWRIGHT_LOOP_UNIT_ID fix)."""
    env_file = tmp_path / "env.sh"
    dangerous = "p3.8; touch pwned"
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", dangerous)

    _run(json.dumps({"session_id": "quote-test-id"}))

    content = env_file.read_text(encoding="utf-8")
    assert "export SHIPWRIGHT_LOOP_UNIT_ID='p3.8; touch pwned'" in content
    # The raw, unquoted form must never appear on its own line.
    assert f"SHIPWRIGHT_LOOP_UNIT_ID={dangerous}\n" not in content


def test_claude_env_file_omits_loop_unit_id_when_unset(monkeypatch, tmp_path):
    env_file = tmp_path / "env.sh"
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_LOOP_UNIT_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))

    _run(json.dumps({"session_id": "no-loop-env-test-id"}))

    content = env_file.read_text(encoding="utf-8")
    assert "SHIPWRIGHT_LOOP_UNIT_ID" not in content


def test_claude_env_file_loop_unit_id_idempotent(monkeypatch, tmp_path):
    env_file = tmp_path / "env.sh"
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "p3.8")

    _run(json.dumps({"session_id": "same-id-2"}))
    _run(json.dumps({"session_id": "same-id-2"}))

    content = env_file.read_text(encoding="utf-8")
    assert content.count("SHIPWRIGHT_LOOP_UNIT_ID=p3.8") == 1


def test_claude_env_file_clears_stale_loop_unit_id_when_next_absent(monkeypatch, tmp_path):
    """Doubt review (trg-33d30377): a stale export from a PREVIOUS unit must not
    linger once a later SessionStart sees the var absent — an append-only write
    would leave it forever, which can make the guard's own documented recovery
    path ("act from the orchestrator's shell once the unit has returned")
    unreachable if this file is shared across a session's Bash-tool calls."""
    env_file = tmp_path / "env.sh"
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))

    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "unit-A")
    _run(json.dumps({"session_id": "sess-1"}))
    assert "SHIPWRIGHT_LOOP_UNIT_ID=unit-A" in env_file.read_text(encoding="utf-8")

    monkeypatch.delenv("SHIPWRIGHT_LOOP_UNIT_ID", raising=False)
    _run(json.dumps({"session_id": "sess-1"}))

    content = env_file.read_text(encoding="utf-8")
    assert "SHIPWRIGHT_LOOP_UNIT_ID" not in content
    assert "export SHIPWRIGHT_SESSION_ID=sess-1" in content


def test_claude_env_file_replaces_loop_unit_id_value_not_accumulates(monkeypatch, tmp_path):
    """A later unit's value must REPLACE an earlier one's line, not add a second
    line for the same var (an env file sourced top-to-bottom would still end up
    correct either way, but a stray old line is exactly the kind of drift the
    doubt review flagged as a hidden coupling risk)."""
    env_file = tmp_path / "env.sh"
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/root")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))

    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "unit-A")
    _run(json.dumps({"session_id": "sess-2"}))
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "unit-B")
    _run(json.dumps({"session_id": "sess-2"}))

    content = env_file.read_text(encoding="utf-8")
    assert "SHIPWRIGHT_LOOP_UNIT_ID=unit-A" not in content
    assert content.count("export SHIPWRIGHT_LOOP_UNIT_ID=unit-B") == 1

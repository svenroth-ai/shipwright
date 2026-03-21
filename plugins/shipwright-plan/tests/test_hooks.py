"""Tests for shipwright-plan hooks."""

import json
import subprocess
import sys
from pathlib import Path

CAPTURE_SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "capture-session-id.py")


def test_capture_session_id_outputs_context(monkeypatch):
    """Test that capture-session-id.py outputs SHIPWRIGHT_ context."""
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/plugin/root")

    payload = json.dumps({"session_id": "test-session-abc"})

    result = subprocess.run(
        [sys.executable, CAPTURE_SCRIPT],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]

    assert "SHIPWRIGHT_SESSION_ID=test-session-abc" in context
    assert "SHIPWRIGHT_PLUGIN_ROOT=/fake/plugin/root" in context
    assert "DEEP_" not in context  # No upstream references


def test_capture_no_session_id():
    """Empty payload → no output."""
    result = subprocess.run(
        [sys.executable, CAPTURE_SCRIPT],
        input="{}",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.stdout.strip() == ""


def test_capture_invalid_json():
    """Invalid JSON → no crash."""
    result = subprocess.run(
        [sys.executable, CAPTURE_SCRIPT],
        input="not json",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0

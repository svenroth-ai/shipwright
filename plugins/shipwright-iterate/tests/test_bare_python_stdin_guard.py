"""bare_python_stdin_guard: deny a bare ``python -`` that would wait on stdin forever.

Origin: two runner subagents emitted ``python - 2>/dev/null; uv run python -c ...`` and
``python - <<'EOF' 2>/dev/null || uv run python - <<'EOF2'`` (loose EOF) and each left a system
Python spinning at 100 % of a core for 15 and 17 hours.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.11")

_HOOK = Path(__file__).resolve().parents[1] / "scripts" / "hooks" / "bare_python_stdin_guard.py"
_spec = importlib.util.spec_from_file_location("bare_python_stdin_guard", _HOOK)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def _payload(command: str, tool: str = "Bash") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"command": command}}


@pytest.mark.parametrize("command", [
    "python - 2>/dev/null; uv run python -c 'print(1)'",
    "python - <<'EOF' 2>/dev/null || uv run python - <<'EOF2'\nprint(1)\nEOF\n",
    "uv run python - <<'EOF'\nprint(1)\n",
    "echo hi && python3 -",
    "uv run python - 2>/dev/null",
    "PYTHONUTF8=1 python -",
    "timeout 600 python -u -",
    "/usr/bin/python3 -",
    "py -",
    "python.exe -",
    "cat foo.py |\n  true\npython -",
    "python 2>/dev/null -",
    "python - <<'PY-END'\nprint(1)",
])
def test_denies_stdin_that_never_ends(command):
    decision = guard.handle_payload(_payload(command))
    assert decision is not None
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("command", [
    "uv run python - <<'EOF'\nx = 1 << n\nprint(x)\nEOF\n",
    "uv run python - <<'EOF'\nprint(1)\nEOF",
    "uv run python -c 'print(1)'",
    "cat script.py | python -",
    "python3 - < script.py",
    "python -m pytest -q",
    "python --version",
    "ls -la",
    "rg -n \"<<'EOF'\" plugins/",
    "grep -c '<<EOF' f",
    "cat <<< hello",
    "tr a-z A-Z <<< hello",
    "uv run python -c \"print(1 << n)\"",
    "echo $((x << y))",
    "git commit -m \"docs: clarify; python - needs stdin\"",
    "cat > notes.md <<'EOF'\npython - 2>/dev/null\nEOF",
    "cat foo.py |\n  python -",
    "python - \\\n  < script.py",
    "uv run python - <<'EOF' 2>/dev/null\nprint(1)\nEOF",
    "echo 'python -'",
    "python \"tools/check.py\" -",
    "uv run python - <<'PY-END'\nprint(1)\nPY-END",
    "uv run python - <<\"9END\"\nprint(1)\n9END",
])
def test_allows_well_formed_commands(command):
    assert guard.handle_payload(_payload(command)) is None


def test_other_tools_and_empty_commands_are_ignored():
    assert guard.handle_payload(_payload("python -", tool="PowerShell")) is None
    assert guard.handle_payload(_payload("   ")) is None


def test_off_switch(monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_BARE_PYTHON_GUARD", "off")
    assert guard.handle_payload(_payload("python -")) is None


def test_main_is_fail_open_on_garbage_stdin():
    result = subprocess.run([sys.executable, str(_HOOK)], input="not json", capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and result.stdout == ""


def test_main_emits_deny_json():
    result = subprocess.run([sys.executable, str(_HOOK)], input=json.dumps(_payload("python -")),
                            capture_output=True, text=True, timeout=30)
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_registered_bash_hook_composes_with_the_worktree_gate():
    """Integration: the command hooks.json really registers, fed a real payload, denies; the gate stays registered beside it."""
    plugin_root = _HOOK.parents[2]
    entries = json.loads((plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    commands = [h["command"] for e in entries if "Bash" in e["matcher"].split("|") for h in e["hooks"]]
    assert any("iterate_worktree_gate.py" in c for c in commands)
    (guard_cmd,) = [c for c in commands if "bare_python_stdin_guard.py" in c]
    script = Path(guard_cmd.split('"')[1].replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root))).resolve()
    assert script == _HOOK.resolve()
    denied = subprocess.run([sys.executable, str(script)], input=json.dumps(_payload("python - 2>/dev/null; uv run python -c 'x'")),
                            capture_output=True, text=True, timeout=30)
    assert json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    allowed = subprocess.run([sys.executable, str(script)], input=json.dumps(_payload("uv run python - <<'EOF'\nprint(1)\nEOF")),
                             capture_output=True, text=True, timeout=30)
    assert allowed.stdout == ""


def test_main_fails_open_when_the_decision_raises(monkeypatch, capsys):
    """An exception inside handle_payload must not deny, crash or print: main() returns 0."""
    import io

    def boom(_payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(guard, "handle_payload", boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_payload("python -"))))
    assert guard.main() == 0
    assert capsys.readouterr().out == ""

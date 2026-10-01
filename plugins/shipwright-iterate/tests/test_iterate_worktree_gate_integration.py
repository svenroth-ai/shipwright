"""Integration: the gate composes with the REAL ``setup_iterate_worktree.py``.

``hooks.json`` + ``hooks/*.py`` make this a ``cross_component`` change, so one
test proves the pieces work together instead of each against a hand-made
fixture: the gate denies in the main checkout, lets the genuine setup command
through, and releases on the pointer that script itself writes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"
sys.path.insert(0, str(HOOK_DIR))
import iterate_worktree_gate as gate  # noqa: E402
from iterate_worktree_gate import handle_payload  # noqa: E402

SESSION = "integ-sess"
SETUP_SCRIPT = gate._SHARED_SCRIPTS / "tools" / "setup_iterate_worktree.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, check=True, capture_output=True,
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("SHIPWRIGHT_PLUGIN_ROOT", "PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", gate._OFF_ENV):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def repo_with_origin(tmp_path) -> Path:
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "-q", "--bare", "-b", "main")
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "shipwright_run_config.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    (root / "a.txt").write_text("x", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    _git(root, "remote", "add", "origin", str(origin))
    _git(root, "push", "-q", "origin", "main")
    return root


def _payload(root: Path, event: str, **extra) -> dict:
    return {"hook_event_name": event, "session_id": SESSION, "cwd": str(root), **extra}


@pytest.mark.covers("FR-01.11/AC40")
def test_real_setup_releases_the_gate(repo_with_origin):
    root = repo_with_origin
    handle_payload(_payload(root, "UserPromptSubmit", prompt="/shipwright-iterate:iterate --type feature x"))
    write = _payload(root, "PreToolUse", tool_name="Write", tool_input={"file_path": str(root / "a.txt")})
    assert handle_payload(write)["hookSpecificOutput"]["permissionDecision"] == "deny"

    # The command the gate's own deny message tells the model to run must itself pass the gate.
    command = f'uv run "{SETUP_SCRIPT}" --project-root . --slug s --run-id iterate-2026-10-01-s'
    setup_call = _payload(root, "PreToolUse", tool_name="Bash", tool_input={"command": command})
    assert handle_payload(setup_call) is None

    done = subprocess.run(
        [sys.executable, str(SETUP_SCRIPT), "--project-root", str(root), "--slug", "s",
         "--run-id", "iterate-2026-10-01-s", "--session-id", SESSION],
        cwd=root, capture_output=True, text=True, timeout=180,
    )
    assert done.returncode == 0, done.stderr
    worktree = Path(json.loads(done.stdout)["project_root"])
    assert worktree.is_dir()

    # cwd is still the main checkout; only the pointer setup wrote has changed.
    assert handle_payload(write) is None
    assert handle_payload(_payload(root, "PreToolUse", tool_name="Bash", tool_input={"command": "rm -rf x"})) is None

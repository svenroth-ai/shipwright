"""Shell-policy / detection hardening tests for ``iterate_worktree_gate`` (split
out of ``test_iterate_worktree_gate_lifecycle.py`` to stay under the 300-line
guideline): creating/writing git forms, ``.git``-file layouts, list-form
campaign args, session-id hint safety, ``record_review_pass`` argument shape."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

HOOK_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"
sys.path.insert(0, str(HOOK_DIR))
import iterate_worktree_gate as gate  # noqa: E402
import iterate_worktree_gate_state as state  # noqa: E402
from iterate_worktree_gate import handle_payload  # noqa: E402
from iterate_worktree_gate_policy import shell_is_preflight_safe  # noqa: E402

COVERS = pytest.mark.covers("FR-01.11/AC40")
SESSION = "sess-1"
BS = chr(92)


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
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _prompt(repo: Path, text: str = "/shipwright-iterate fix it") -> dict:
    return {"hook_event_name": "UserPromptSubmit", "session_id": SESSION, "cwd": str(repo), "prompt": text}


def _tool(cwd: Path, name: str, **tool_input) -> dict:
    return {
        "hook_event_name": "PreToolUse", "session_id": SESSION, "cwd": str(cwd),
        "tool_name": name, "tool_input": tool_input,
    }


@COVERS
@pytest.mark.parametrize("command", [
    "git branch -v newbranch", "git branch -vv newbranch", "git branch newbranch",
    "git diff --output=x.txt", "git ls-remote --upload-pack=x .", "git worktree remove ../other", "git worktree prune", "git worktree remove --force /srv/x", "git worktree remove .worktrees/../..", "git branch -D main", "git branch -D iterate/a main", "git -c diff.external=touch diff --ext-diff", "git -c core.pager=x log", "git diff --ext-diff", "git log --output x", "git fetch origin main:newbranch", "git fetch --all",
])
def test_creating_or_writing_git_forms_are_denied(repo, command):
    handle_payload(_prompt(repo))
    assert handle_payload(_tool(repo, "Bash", command=command))["hookSpecificOutput"]["permissionDecision"] == "deny"


@COVERS
@pytest.mark.parametrize("command", ["git worktree list", "git branch --list 'iterate/*'", "git branch -vv"])
def test_non_creating_git_forms_stay_allowed(repo, command):
    handle_payload(_prompt(repo))
    assert handle_payload(_tool(repo, "Bash", command=command)) is None



@COVERS
def test_separate_git_dir_under_a_worktrees_path_is_not_isolation(tmp_path):
    """A ``.git`` file pointing at ``.../worktrees/x.git`` is not a linked worktree."""
    fake = tmp_path / "srv" / "worktrees" / "project.git"
    fake.mkdir(parents=True)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").write_text(f"gitdir: {fake}\n", encoding="utf-8")
    assert state._linked_worktree_by_dotgit(checkout) is None


@COVERS
def test_campaign_flag_in_list_form_args_is_detected():
    assert gate._is_campaign(None, {"args": ["--campaign", "x"]})
    assert not gate._is_campaign(None, {"args": ["fix it"]})


@COVERS
def test_unsafe_session_id_is_not_echoed_into_the_hint():
    assert "--session-id" not in gate._setup_hint("a b; rm -rf x")
    assert "--session-id abc-123" in gate._setup_hint("abc-123")


@pytest.mark.parametrize("command", [
    "uv run /x/record_review_pass.py --project-root . show",
    "uv run /x/record_review_pass.py --mode record-x show",
])
def test_record_review_pass_allows_only_show_as_first_argument(command):
    assert not shell_is_preflight_safe({"command": command})


@COVERS
@pytest.mark.parametrize("config", ['{"status": "in_progress"}', "{}", "not json"])
def test_project_the_skill_would_refuse_is_never_armed(repo, config):
    (repo / "shipwright_run_config.json").write_text(config, encoding="utf-8")
    assert handle_payload(_prompt(repo)) is None
    assert handle_payload(_tool(repo, "Bash", command="rm -rf x")) is None


@COVERS
def test_iterate_history_alone_makes_a_project_eligible(repo):
    (repo / "shipwright_run_config.json").write_text('{"iterate_history": [{"run_id": "r"}]}', encoding="utf-8")
    assert handle_payload(_prompt(repo)) is not None


@COVERS
@pytest.mark.parametrize("command", [
    "echo hi\rRemove-Item a.txt",
    "echo hi\r\nRemove-Item a.txt",
    "echo hi\nrm x",
])
def test_line_breaks_never_hide_a_second_statement(command):
    """A bare CR is a statement break in PowerShell; shlex would read it as whitespace."""
    assert not shell_is_preflight_safe({"command": command})
    assert not shell_is_preflight_safe({"command": command.replace("echo hi", "git status")})


@COVERS
def test_backslash_newline_continuation_is_bash_only(repo):
    """In PowerShell a trailing backslash is a literal and the newline starts a new statement."""
    command = "Get-Content a.txt " + BS + chr(10) + "Remove-Item a.txt"
    assert not shell_is_preflight_safe({"command": command}, powershell=True)
    handle_payload(_prompt(repo))
    assert handle_payload(_tool(repo, "PowerShell", command=command))["hookSpecificOutput"]["permissionDecision"] == "deny"
    folded = "ls " + BS + chr(10) + "  -la"  # the documented bash continuation still folds into one command
    assert shell_is_preflight_safe({"command": folded})
    assert not shell_is_preflight_safe({"command": folded}, powershell=True)

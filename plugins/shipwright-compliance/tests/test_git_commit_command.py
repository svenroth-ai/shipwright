"""``git_commit_command.is_git_commit``: comments, shell compound syntax, string-running programs (U9)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "lib"))
import git_commit_command as gcc  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.10")


@pytest.mark.parametrize("command", [
    # '#' is not a lexer comment: it must not swallow the rest of the flattened line
    "# note\ngit add -A\ngit commit -m x",
    "curl http://h/#a && git commit -m x",
    # leading shell reserved words
    "if ! git diff --cached --quiet; then git commit -m x; fi",
    "for f in a; do git commit -m x; done",
    "while true; do git commit -m x; done",
    "until false; do git commit -m x; done",
    "if a; then b; elif c; then d; else git commit -m x; fi",
    "{ git commit -m x; }",
    "! git commit",
    "then env FOO=1 git commit",
    # programs that run a command string
    'eval "git commit -m x"',
    "eval git commit -m x",
    'pwsh -NoProfile -Command "git commit -m x"',
    'powershell.exe -NoProfile -NonInteractive -c "git add .; git commit -m x"',
    'pwsh -ExecutionPolicy Bypass -Com "git commit"',
    'cmd /c "git commit -m x"',
    "cmd.exe /d /C git commit -m x",
    "cmd //c git commit",
    "bash -c 'eval \"git commit\"'",
])
def test_real_commits_fire(command):
    assert gcc.is_git_commit(command)


@pytest.mark.parametrize("command", [
    "# git commit",
    "  # git commit -m x",
    'eval "echo git commit"',
    "eval",
    'pwsh -Command "echo git commit"',
    "pwsh -File x.ps1 git commit",
    "pwsh -NoProfile",
    'cmd /c "echo git commit"',
    "cmd /c",
    "cmd",
    "if git status; then echo ok; fi",
    "echo '#' git commit",
    "for git in commit; do echo $git; done",
])
def test_non_commits_do_not_fire(command):
    assert not gcc.is_git_commit(command)


def test_string_running_programs_share_the_depth_bound():
    depth = gcc._MAX_SHELL_DEPTH
    assert gcc.is_git_commit("cmd /c " * depth + "git commit")
    assert not gcc.is_git_commit("cmd /c " * (depth + 1) + "git commit")
    assert gcc.is_git_commit("eval " * depth + "git commit")
    assert not gcc.is_git_commit("eval " * (depth + 1) + "git commit")
    assert not gcc._segment_is_commit(["eval", "git commit"], gcc._MAX_SHELL_DEPTH)
    assert not gcc._segment_is_commit(["cmd", "/c", "git commit"], gcc._MAX_SHELL_DEPTH)
    assert not gcc._segment_is_commit(["pwsh", "-c", "git commit"], gcc._MAX_SHELL_DEPTH)
    assert gcc._segment_is_commit(["pwsh", "-c", "git commit"], gcc._MAX_SHELL_DEPTH - 1)

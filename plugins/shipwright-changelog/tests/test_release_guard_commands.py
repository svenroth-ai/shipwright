"""Which command lines the release guard treats as an outward release action (unit P4b, FR-01.09; pure text, no git)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "hooks"))
from release_guard_commands import find_actions  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.09/AC01")


def one(command: str):
    found = find_actions(command)
    assert len(found) == 1, found
    return found[0]


@pytest.mark.parametrize("command", [
    "git push --tags origin main",  # FULLRUN-REPORT forms
    "git push origin HEAD",
    "git push origin main refs/tags/v1.2.3",
    "git push origin v1.2.3",
    "git push origin tag v1.2.3",
    "git push --follow-tags",
    "git push origin main",
    "git push origin HEAD:main",
    "git push --force-with-lease origin +feature:refs/heads/main",
    "git push --all",
    "git push",
    "git -C /work/repo push origin main",
    r"git -C C:\Users\dev\repo push --tags origin main",
    'git -C "C:\\Users\\dev\\my repo" push origin main',
    "cd /x && git push origin main",
    "FOO=1 git push origin main",
    "git.exe push origin main",
    "/usr/bin/git push origin main",
    "git add . && git commit -m x && git push origin main 2>&1",
    "git push origin main > out.txt",
])
def test_a_git_push_is_found(command):
    assert one(command).kind == "push"


@pytest.mark.parametrize("command", ["gh pr merge", "gh pr merge --merge --delete-branch", "gh pr merge 12 --auto",
                                     "gh -R owner/repo pr merge 12", "gh pr merge --repo o/r 12"])
def test_gh_pr_merge_is_found(command):
    assert one(command).kind == "merge"


@pytest.mark.parametrize("command", ["gh release create v1.0.0", "gh release create v1.0.0 --verify-tag --notes x"])
def test_gh_release_create_is_found(command):
    assert one(command).kind == "release"


@pytest.mark.parametrize("command", [
    "git status", "git commit -m 'git push origin main'", 'git commit -m "gh pr merge"', "echo 'git push --tags'",
    "gh pr create --title x", "gh pr view 12", "gh release list", "gh release view v1", "git log --grep push",
    "rg 'git push' docs", "git fetch origin main", "git tag -a v1 -m x", "# git push origin main", "ls && pwd",
    "git commit -m \"$(cat <<'EOF'\nfix: x\n\ngit push origin main\nEOF\n)\"", "cat <<EOF\ngit push origin main\nEOF",
    'git commit --message="wip; git push --tags origin main"',
    '$m = @"' + chr(10) + 'git push --tags origin main' + chr(10) + '"@' + chr(10) + 'git commit -m $m',
    'gh issue create --body="x' + chr(10) + 'gh pr merge 42' + chr(10) + 'y"',
    "git commit --message='a && gh release create v1'",
    "", "   ", "git push 'unbalanced",
])
def test_everything_else_is_not_an_action(command):
    assert find_actions(command) == []


def test_windows_dash_c_path_is_kept_whole():
    assert one(r"git -C C:\Users\dev\repo push origin main").c_paths == [r"C:\Users\dev\repo"]
    assert one('git -C "C:\\Users\\dev\\my repo" push origin main').c_paths == [r"C:\Users\dev\my repo"]


def test_refspecs_are_reduced_to_their_destination():
    act = one("git push origin +HEAD:refs/heads/main feature:other refs/tags/v1")
    assert act.refs == ["main", "other"] and act.tags
    assert one("git push origin").refs == []
    assert one("git push --tags").tags
    assert one("git push --mirror").all_refs


def test_a_second_command_in_the_line_is_found():
    kinds = [a.kind for a in find_actions("git push origin feature && gh pr merge 3 --merge")]
    assert kinds == ["push", "merge"]

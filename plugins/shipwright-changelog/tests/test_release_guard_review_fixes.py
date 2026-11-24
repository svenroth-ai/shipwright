"""Review fixes of unit P4b: PowerShell, the release's own PR, ``cd``, ``--repo``, event-only history, and what the deny says."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from lib import release_runstate

from .test_release_guard import HOOK, VERSION, blocked, git, record, repo as _repo, run_hook, start_release
sys.path.insert(0, str(HOOK.parent))
from release_guard_commands import find_actions  # noqa: E402

repo = _repo  # the fixture, re-exported so pytest finds it in this module
pytestmark = pytest.mark.covers("FR-01.09/AC01")


def _patch_state(work, **fields):
    path = release_runstate.state_path(work)
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, **fields}), encoding="utf-8")


def test_the_powershell_tool_is_guarded_too(repo):
    start_release(repo)
    assert blocked(run_hook("git push --tags origin main", repo, tool_name="PowerShell"))
    assert blocked(run_hook("& git push origin main; gh pr merge", repo, tool_name="PowerShell"))
    assert run_hook("git push origin main", repo, tool_name="Read") is None


def test_hooks_json_matches_both_shell_tools():
    path = HOOK.parents[2] / "hooks" / "hooks.json"
    entries = json.loads(path.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert [e["matcher"] for e in entries] == ["Bash|PowerShell"]


def test_only_the_releases_own_merge_is_held(repo):
    start_release(repo)
    _patch_state(repo, branch="release/v1.2.3", pr_url="https://github.com/o/r/pull/42")
    git(repo, "checkout", "-b", "release/v1.2.3")
    assert blocked(run_hook("gh pr merge", repo))  # the current branch is the release branch
    assert blocked(run_hook("gh pr merge 42 --merge", repo))
    assert blocked(run_hook("gh pr merge https://github.com/o/r/pull/42", repo))
    assert blocked(run_hook("gh pr merge release/v1.2.3", repo))
    assert run_hook("gh pr merge 7 --squash", repo) is None  # a sibling PR
    git(repo, "checkout", "-b", "iterate/other")
    assert run_hook("gh pr merge", repo) is None  # the current branch's PR is not the release's


def test_another_repository_is_not_this_checkout(repo):
    start_release(repo)
    assert run_hook("gh -R owner/other pr merge 3", repo) is None
    assert run_hook("gh release create v9.9.9 --repo owner/other", repo) is None


def test_cd_aims_the_check_at_the_target_repository(repo, tmp_path):
    start_release(repo)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert blocked(run_hook(f'cd "{repo}" && git push --tags origin main', elsewhere))
    assert run_hook(f'cd "{elsewhere}" && git push origin main', repo) is None


def test_cd_is_carried_into_the_parsed_action():
    (act,) = find_actions("cd /work/repo && git -C sub push origin main")
    assert act.c_paths == ["/work/repo", "sub"]
    (act,) = find_actions("Set-Location C:\\repo; git push --tags")
    assert act.c_paths == ["C:\\repo"]


def test_repo_option_names_the_remote_so_the_rest_are_refspecs():
    assert find_actions("git push --repo origin main")[0].refs == ["main"]
    assert find_actions("git push --repo=origin main")[0].refs == ["main"]
    assert find_actions("git push origin main")[0].refs == ["main"]


def test_a_change_and_its_revert_is_not_an_event_commit(repo):
    start_release(repo)
    record(repo)
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    git(repo, "commit", "-am", "code change")
    git(repo, "revert", "--no-edit", "HEAD")
    assert git(repo, "diff", "--name-only", "HEAD~2", "HEAD") == ""  # the net tree is the release's, the history is not
    assert blocked(run_hook("git push origin main", repo))


def test_a_version_shaped_branch_is_not_a_tag(repo):
    start_release(repo)
    git(repo, "checkout", "-b", "2.0-hotfix")
    assert run_hook("git push -u origin 2.0-hotfix", repo) is None


def test_the_command_text_cannot_lift_the_guard(repo):
    start_release(repo)
    assert blocked(run_hook("SHIPWRIGHT_RELEASE_GUARD=off git push --tags origin main", repo))


def test_the_deny_does_not_tell_the_model_to_delete_the_state(repo):
    start_release(repo)
    reason = run_hook("git push origin main", repo)["permissionDecisionReason"]
    assert "ask the user" in reason and "commit-and-tag" in reason and f"v{VERSION}" in reason
    assert "delete the run state" not in reason


def test_a_non_dict_run_state_fails_open(repo):
    release_runstate.state_path(repo).parent.mkdir(parents=True, exist_ok=True)
    release_runstate.state_path(repo).write_text("[1, 2]", encoding="utf-8")
    assert run_hook("git push origin main", repo) is None


def test_a_crlf_command_is_read(repo):
    start_release(repo)
    assert blocked(run_hook("git status\r\ngit push --tags origin main\r\n", repo))


def test_the_hook_is_one_process_that_never_writes_stdout_for_an_allow(repo):
    done = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0 and done.stdout == ""

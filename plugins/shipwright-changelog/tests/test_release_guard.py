"""The release guard hook against real git (unit P4b, FR-01.09): blocks an outward release action while a release is in progress
without its record for HEAD, and never blocks an ordinary push.

The run state and the record are written by the producers (``release_runstate.save``, ``release_commit.write_state``), so the
hook is tested against the bytes the release really leaves behind.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lib import release_commit, release_runstate

HOOK = Path(__file__).resolve().parents[1] / "scripts" / "hooks" / "release_guard.py"
pytestmark = pytest.mark.covers("FR-01.09/AC01")
VERSION = "1.2.3"


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = t\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("SHIPWRIGHT_RELEASE_GUARD", raising=False)
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, capture_output=True)
    (work / "a.txt").write_text("a\n", encoding="utf-8")
    git(work, "add", "a.txt")
    git(work, "commit", "-m", "init")
    git(work, "push", "origin", "main")
    return work


def start_release(work: Path, *, age_hours: int = 0) -> None:
    made = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    release_runstate.save(work, {"schema": 1, "version": VERSION, "release_date": made.strftime("%Y-%m-%d"), "run_id": "r1",
                                 "created_at": made.isoformat(timespec="seconds")})


def record(work: Path, commit: str | None = None, version: str = VERSION) -> None:
    release_commit.write_state(work, {"schema": 1, "version": version, "tag": f"v{version}", "commit": commit or git(work, "rev-parse", "HEAD"),
                                      "checks_passed": ["commit"], "tagged_at": "2026-11-23T00:00:00+00:00"})


def run_hook(command: str, cwd: Path, **payload) -> dict | None:
    body = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd), **payload}
    done = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(body), capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr  # never a hard exit: the block is the deny decision
    return json.loads(done.stdout)["hookSpecificOutput"] if done.stdout.strip() else None


def blocked(out: dict | None) -> bool:
    return bool(out) and out["permissionDecision"] == "deny"


OUTWARD = ["git push --tags origin main", "git push origin main", "git push origin HEAD", "git push origin v1.2.3",
           "git push origin main refs/tags/v1.2.3", "gh pr merge --merge --delete-branch", "gh release create v1.2.3"]


@pytest.mark.parametrize("command", OUTWARD)
def test_blocks_every_outward_action_without_a_record(repo, command):
    start_release(repo)
    out = run_hook(command, repo)
    assert blocked(out) and f"v{VERSION}" in out["permissionDecisionReason"]


@pytest.mark.parametrize("command", OUTWARD)
def test_old_behaviour_nothing_blocks_without_the_hook(repo, command):
    """The fails-on-old half: with no release in progress, the same commands are allowed (what ran before the hook existed)."""
    assert run_hook(command, repo) is None


@pytest.mark.parametrize("command", OUTWARD)
def test_allows_with_the_record_for_head(repo, command):
    start_release(repo)
    record(repo)
    assert run_hook(command, repo) is None


@pytest.mark.parametrize("command", ["git push origin feature", "git push -u origin my-branch", "git status", "git commit -m x",
                                     "gh pr create --title x", "gh release list", "git push origin HEAD:feature"])
def test_an_ordinary_command_is_never_blocked_even_mid_release(repo, command):
    start_release(repo)
    git(repo, "checkout", "-b", "feature")
    assert run_hook(command, repo) is None


def test_head_on_a_feature_branch_is_not_a_trunk_push(repo):
    start_release(repo)
    git(repo, "checkout", "-b", "release/v1.2.3")
    assert run_hook("git push origin HEAD", repo) is None
    assert run_hook("git push", repo) is None
    assert blocked(run_hook("git push origin main", repo))


def test_a_record_for_a_different_commit_blocks(repo):
    start_release(repo)
    record(repo, commit=git(repo, "rev-parse", "HEAD"))
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")
    git(repo, "commit", "-am", "later work")
    out = run_hook("git push origin main", repo)
    assert blocked(out) and "but HEAD is" in out["permissionDecisionReason"] and "does not exist" not in out["permissionDecisionReason"]


def test_a_record_of_another_version_blocks(repo):
    start_release(repo)
    record(repo, version="0.9.0")
    assert blocked(run_hook("gh pr merge", repo))


def test_head_after_the_event_commit_is_still_the_release(repo):
    """``record-event`` commits after ``commit-and-tag``: that one event-only commit must not make the record stale."""
    start_release(repo)
    record(repo)
    (repo / "shipwright_events.jsonl").write_text("{}\n", encoding="utf-8")
    (repo / ".shipwright/events/drops").mkdir(parents=True)
    (repo / ".shipwright/events/drops/e1.json").write_text("{}\n", encoding="utf-8")
    git(repo, "add", "shipwright_events.jsonl", ".shipwright/events/drops")
    git(repo, "commit", "-m", "chore(release): record changelog event")
    assert run_hook("gh pr merge", repo) is None
    (repo / "a.txt").write_text("x\n", encoding="utf-8")
    git(repo, "commit", "-am", "not an event")
    assert blocked(run_hook("gh pr merge", repo))


def test_inert_once_the_tag_is_on_origin(repo):
    start_release(repo)
    assert blocked(run_hook("git push origin main", repo))
    git(repo, "tag", f"v{VERSION}")
    git(repo, "push", "origin", f"v{VERSION}")
    git(repo, "commit", "--allow-empty", "-m", "next work")
    assert run_hook("git push origin main", repo) is None


def test_an_unreachable_origin_keeps_the_deny(repo):
    """The tag lookup is the one error that does not fail open: with no origin to ask, the release is not known to be out."""
    start_release(repo)
    git(repo, "remote", "remove", "origin")
    assert blocked(run_hook("git push origin main", repo))


def test_an_abandoned_release_older_than_48_hours_is_inert(repo):
    start_release(repo, age_hours=49)
    assert run_hook("git push origin main", repo) is None


def test_another_project_roots_state_is_not_this_releases(repo, tmp_path):
    start_release(repo)
    other = json.loads(release_runstate.state_path(repo).read_text(encoding="utf-8"))
    other["project_root"] = (tmp_path / "elsewhere").resolve().as_posix()
    release_runstate.state_path(repo).write_text(json.dumps(other), encoding="utf-8")
    assert run_hook("git push origin main", repo) is None


def test_dash_c_aims_the_check_at_that_repository(repo, tmp_path):
    start_release(repo)
    assert blocked(run_hook(f'git -C "{repo}" push origin main', tmp_path))  # a Windows drive path here, a POSIX one elsewhere
    assert run_hook(f'git -C "{tmp_path}" push origin main', repo) is None  # tmp_path is no repository


def test_off_switch_lifts_the_guard(repo, monkeypatch):
    start_release(repo)
    monkeypatch.setenv("SHIPWRIGHT_RELEASE_GUARD", "off")
    assert run_hook("git push origin main", repo) is None


@pytest.mark.parametrize("raw", ["", "not json", "[]", '{"tool_input": "str"}', '{"tool_name": "Bash", "tool_input": {"command": 5}}',
                                 '{"tool_name": "Bash", "tool_input": {"command": "git push origin main"}, "cwd": 7}'])
def test_garbled_payloads_fail_open(raw):
    done = subprocess.run([sys.executable, str(HOOK)], input=raw, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0 and "deny" not in done.stdout


def test_a_corrupt_run_state_or_a_missing_cwd_fails_open(repo, tmp_path):
    release_runstate.state_path(repo).parent.mkdir(parents=True, exist_ok=True)
    release_runstate.state_path(repo).write_text("{ torn", encoding="utf-8")
    assert run_hook("git push origin main", repo) is None
    assert run_hook("git push origin main", tmp_path / "does-not-exist") is None

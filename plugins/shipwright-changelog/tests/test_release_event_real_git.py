"""``release.py record-event`` against real git and a bare remote (the old ``SKILL.md`` fenced-block behaviour tests, moved with the chain).

Before unit P4 the Step 7 event blocks were shell chains the model ran, and this file's predecessor extracted them from ``SKILL.md`` and
executed them. The chain is code now (``release_event.record_event``), so the same behaviours are asserted on the code: git is real, and only
the two Shipwright tools it calls (``record_event.py``, ``stage_event_drops.py``) are stubs, as they were before (the real ones are covered in
``shared/tests`` and by the golden scenarios).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lib import release_event
from lib.release_runner import CmdResult, Recorder, subprocess_runner

pytestmark = pytest.mark.covers("FR-01.09/AC01")
VERSION = "1.2.3"


class Tools:
    """git runs for real; the event tools are stubs. ``fail``: record_event exits 1; ``noop``: exits 0 and writes nothing (dedup)."""

    def __init__(self, fail: bool = False, noop: bool = False) -> None:
        self.fail, self.noop = fail, noop

    def __call__(self, key, argv, cwd):
        if key == "event-record":
            if self.fail:
                return CmdResult(key, tuple(argv), 1, "", "record_event failed")
            if not self.noop:
                with open(Path(cwd) / "shipwright_events.jsonl", "a", encoding="utf-8") as handle:
                    handle.write('{"event": "phase_completed"}\n')
            return CmdResult(key, tuple(argv), 0)
        if key == "event-stage":  # legacy layout: the real tool is a no-op that exits 0
            return CmdResult(key, tuple(argv), 0)
        return subprocess_runner(key, argv, cwd)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True, encoding="utf-8").stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = t\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, capture_output=True)
    (work / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    git(work, "add", "CHANGELOG.md")
    git(work, "commit", "-m", "init")
    git(work, "push", "origin", "main")
    return work, remote


def record(work: Path, plugin_root: Path, tools: Tools | None = None):
    return release_event.record_event(Recorder(tools or Tools(), work), plugin_root, version=VERSION, pr_url="https://example.invalid/pr/1")


def test_pr_flow_commits_only_the_events_file_and_pushes_the_branch(repo, plugin_root):
    work, remote = repo
    git(work, "checkout", "-b", "release/v1.2.3")
    (work / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    git(work, "add", "shipwright_events.jsonl")
    git(work, "commit", "-m", "events file exists")
    (work / "CHANGELOG.md").write_text("# Changelog\n\n## 1.2.3\n", encoding="utf-8")  # an unrelated edit stays out of the event commit
    code, out = record(work, plugin_root)
    assert code == 0, out
    assert git(work, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD") == "shipwright_events.jsonl"
    assert "record changelog event for v1.2.3" in git(work, "log", "-1", "--format=%s")
    assert git(work, "status", "--porcelain") == "M CHANGELOG.md"
    assert git(remote, "rev-parse", "release/v1.2.3") == git(work, "rev-parse", "HEAD")


def test_pr_flow_handles_a_first_release_with_an_untracked_events_file(repo, plugin_root):
    work, remote = repo
    git(work, "checkout", "-b", "release/v1.2.3")
    assert record(work, plugin_root)[0] == 0
    assert git(work, "ls-tree", "--name-only", "HEAD").split() == ["CHANGELOG.md", "shipwright_events.jsonl"]
    assert git(remote, "rev-parse", "release/v1.2.3")


def test_on_main_commits_but_pushes_nothing(repo, plugin_root):
    work, remote = repo
    before = git(remote, "rev-parse", "main")
    code, out = record(work, plugin_root)
    assert code == 0 and out["pushed"] is False and out["on_trunk"] is True
    assert git(work, "rev-parse", "HEAD") != before and "record changelog event for v1.2.3" in git(work, "log", "-1", "--format=%s")
    assert git(remote, "rev-parse", "main") == before


@pytest.mark.parametrize("branch", ["release/v1.2.3", "main"], ids=["pr-flow", "on-main"])
def test_a_failing_record_event_stops_before_commit_and_push(repo, plugin_root, branch):
    work, remote = repo
    if branch != "main":
        git(work, "checkout", "-b", branch)
    head, remote_main = git(work, "rev-parse", "HEAD"), git(remote, "rev-parse", "main")
    code, _ = record(work, plugin_root, Tools(fail=True))
    assert code != 0 and git(work, "rev-parse", "HEAD") == head and git(work, "diff", "--cached", "--name-only") == ""
    assert "release/v1.2.3" not in git(remote, "branch", "--list") and git(remote, "rev-parse", "main") == remote_main


def test_pr_flow_retries_the_push_when_record_event_records_nothing(repo, plugin_root):
    """``record_event.py`` exits 0 without writing when the event exists (dedup): a re-run after a push that did not land must push."""
    work, remote = repo
    git(work, "checkout", "-b", "release/v1.2.3")
    assert record(work, plugin_root)[0] == 0
    git(remote, "update-ref", "-d", "refs/heads/release/v1.2.3")  # the push is lost
    head = git(work, "rev-parse", "HEAD")
    assert record(work, plugin_root, Tools(noop=True))[0] == 0
    assert git(work, "rev-parse", "HEAD") == head and git(remote, "rev-parse", "release/v1.2.3") == head


def test_on_main_succeeds_when_record_event_records_nothing(repo, plugin_root):
    work, _ = repo
    (work / "shipwright_events.jsonl").write_text("{}\n", encoding="utf-8")
    git(work, "add", "shipwright_events.jsonl")
    git(work, "commit", "-m", "event recorded earlier")
    head = git(work, "rev-parse", "HEAD")
    assert record(work, plugin_root, Tools(noop=True))[0] == 0 and git(work, "rev-parse", "HEAD") == head

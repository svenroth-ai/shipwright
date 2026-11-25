"""The behaviour changes the operator decided at stop 2 (2026-11-23), each proven on real git and the gh stub (unit P4).

Every test names the OLD behaviour it fails on: the pinned prose of today's ``SKILL.md`` pushed ``git push --tags origin main``
from any branch (F1a), pushed the tag while a guided release's PR was open (F1b), carried on after a failed ``gh pr create``
or a rejected push (F4, F6), wrote the dashboard, the handover note and ``phase_history`` in a hand-invoked release and left
the tree dirty (F10), and never checked the tag against the CHANGELOG outside the orchestrator's ``update-step`` (F7). B1 and B4
are proven through the CLI driver on a complete release.
"""

from __future__ import annotations

import json
import stat
from typing import Any

import pytest

from . import scenario_support as ss
from .driver_cli import CliDriver
from .driver_replay import ReplayDriver
from .replay_commands import CLOSE_PHASE, PLUGIN, SHARED, fill
from .scenario_core import release_flow

VERSION = "1.3.0"
DRIVERS = pytest.mark.parametrize("driver_class", [ReplayDriver, CliDriver], ids=["replay", "cli"])
pytestmark = pytest.mark.covers("FR-01.09/AC01")
ADVISORY = "?? .shipwright/triage.jsonl"  # the release audit's advisory finding, untracked on some systems (scenarios_release S1 pins it)


def _remote(s: Any, *args: str) -> str:
    return s.git("--git-dir", s.origin.as_posix(), *args)


def _remote_tags(s: Any) -> list[str]:
    return s.git("ls-remote", "--tags", s.origin.as_posix()).split()


def _steps(results) -> list[str]:
    return [r.step for r in results]


def _close_hook(s: Any, script: bytes) -> None:
    hook = s.origin / "hooks" / "pre-receive"
    hook.parent.mkdir(exist_ok=True)
    hook.write_bytes(script)
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.mark.covers("FR-01.09/AC11")
@DRIVERS
def test_f1b_a_guided_release_pushes_no_tag_and_makes_no_page_before_the_pr_is_merged(make_project, driver_class):
    s = ss.ready_release(make_project)
    driver = driver_class()
    results = release_flow(driver, s, "guided")
    assert all(r.exit_code == 0 for r in results) and {"push-tags", "release-page"}.isdisjoint(_steps(results))
    assert f"v{VERSION}" in s.git("tag").split() and f"refs/tags/v{VERSION}" not in " ".join(_remote_tags(s))  # the old flow pushed it here
    assert [p["state"] for p in s.gh_state()["prs"]] == ["open"] and s.gh_state()["releases"] == {}
    assert driver.name in ("replay", "cli")


@pytest.mark.covers("FR-01.09/AC11")
@DRIVERS
def test_f1a_from_a_feature_branch_only_the_tag_is_pushed_and_never_the_local_trunk(make_project, driver_class):
    s = ss.ready_release(make_project, autonomy="autonomous")
    driver = driver_class()
    results = release_flow(driver, s, "autonomous", skip=("push-tags",))  # a merged PR, the tag not pushed yet
    assert all(r.exit_code == 0 for r in results)
    s.git("checkout", "-q", "-b", "release/after-merge")  # the person is back on a feature branch ...
    s.git("commit", "-q", "--allow-empty", "-m", "chore: local work that was never pushed")
    s.git("branch", "-f", "main", "HEAD")  # ... while the local trunk holds that unpushed work
    trunk_before = _remote(s, "rev-parse", "main")
    pushed = driver.run_step("push-tags", s)
    assert pushed.exit_code == 0 and _remote(s, "rev-parse", "main") == trunk_before  # the old `--tags origin main` moved the remote trunk
    assert f"refs/tags/v{VERSION}" in " ".join(_remote_tags(s))


@pytest.mark.covers("FR-01.09/AC11")
@DRIVERS
def test_f1a_on_the_trunk_the_trunk_is_still_pushed_with_the_tag(make_project, driver_class):
    s = ss.ready_release(make_project, branch=None)
    results = release_flow(driver_class(), s, "guided")
    assert all(r.exit_code == 0 for r in results) and "push-tags" in _steps(results)
    assert s.git("rev-parse", "main") == _remote(s, "rev-parse", "main") and f"refs/tags/v{VERSION}" in " ".join(_remote_tags(s))


def _gh_missing(s: Any):
    def hook() -> None:
        s.env["SHIPWRIGHT_TEST_GH_ARGV_PREFIX"] = json.dumps(["gh-is-not-installed-here"])
    return hook


@DRIVERS
def test_f4_a_failed_pr_creation_stops_the_release_before_any_tag_reaches_the_remote(make_project, driver_class):
    s = ss.ready_release(make_project)
    results = release_flow(driver_class(), s, "guided", before={"open-pr": _gh_missing(s)})
    assert _steps(results)[-1] == "open-pr" and results[-1].exit_code == 127
    assert {"record-event", "push-tags", "release-page"}.isdisjoint(_steps(results))  # the old flow went on and pushed the tag
    assert f"refs/tags/v{VERSION}" not in " ".join(_remote_tags(s)) and f"v{VERSION}" in s.git("tag").split()


@pytest.mark.parametrize("flavour", ["tag-push-refused"])
@DRIVERS
def test_f4_a_failed_tag_push_stops_the_release_and_no_page_follows(make_project, driver_class, flavour):
    s = ss.ready_release(make_project, autonomy="autonomous")
    _close_hook(s, b'#!/bin/sh\nwhile read old new ref; do case "$ref" in refs/tags/*) echo "pre-receive: tags are closed" >&2; exit 1;; esac; done\nexit 0\n')
    results = release_flow(driver_class(), s, "autonomous")
    assert _steps(results)[-1] == "push-tags" and results[-1].exit_code != 0 and "release-page" not in _steps(results)
    assert f"refs/tags/v{VERSION}" not in " ".join(_remote_tags(s)) and s.gh_state()["releases"] == {}


@DRIVERS
def test_f6_the_flow_stops_after_a_rejected_push_as_the_and_chain_of_skill_341_says(make_project, driver_class):
    s = ss.ready_release(make_project)

    def close() -> None:  # P8a (F3): the branch is pushed before the PR now; the remote closes before the event push
        _close_hook(s, b'#!/bin/sh\necho "pre-receive: pushes are closed" >&2\nexit 1\n')

    results = release_flow(driver_class(), s, "guided", before={"record-event": close})
    assert _steps(results)[-1] == "record-event" and results[-1].exit_code != 0  # the old replay went on to push the tag and make a page
    assert {"push-tags", "release-page"}.isdisjoint(_steps(results)) and _remote_tags(s) == [
        t for t in _remote_tags(s) if "v1.3.0" not in t]


def _standalone_flow(make_project, **kw):
    s = ss.ready_release(make_project, autonomy="autonomous", **kw)
    driver = CliDriver()
    return s, driver, release_flow(driver, s, "autonomous", close=True)


def _porcelain(s: Any) -> list[str]:
    return [line for line in s.git("status", "--porcelain").splitlines() if line != ADVISORY]


@pytest.mark.covers("FR-01.09/AC01")
def test_f10_a_hand_invoked_release_leaves_a_clean_tree_with_nothing_written_by_the_close(make_project):
    s = ss.ready_release(make_project, autonomy="autonomous")
    driver = CliDriver()
    before = {}
    results = release_flow(driver, s, "autonomous", close=True, before={"close-phase": lambda: before.update(
        config=(s.repo / "shipwright_run_config.json").read_bytes(), dashboard=s.git("rev-parse", "HEAD:.shipwright/agent_docs/build_dashboard.md"))})
    assert results[-1].step == "close-phase" and results[-1].exit_code == 0, [(r.step, r.exit_code) for r in results]
    assert _porcelain(s) == []  # `git status --porcelain`: nothing the release wrote is left over
    assert not (s.repo / ".shipwright/agent_docs/session_handoff.md").exists()  # no handover note in a hand-invoked release
    assert (s.repo / "shipwright_run_config.json").read_bytes() == before["config"]  # no phase_history write
    assert s.git("rev-parse", "HEAD:.shipwright/agent_docs/build_dashboard.md") == before["dashboard"]
    assert "update-step" not in json.dumps([c["stdout"] + c["stderr"] for c in driver.log])  # F7: the orchestrator is not involved


@pytest.mark.covers("FR-01.09/AC01")
def test_f10_the_old_close_block_left_the_tree_dirty_and_the_dashboard_changed(make_project):
    """The pinned prose's block (replay_commands.CLOSE_PHASE) on the same finished release: it writes the three files."""
    s = ss.ready_release(make_project, autonomy="autonomous")
    release_flow(ReplayDriver(), s, "autonomous")
    script = fill(CLOSE_PHASE, version=VERSION, shared=SHARED.as_posix(), plugin=PLUGIN.as_posix(), session="old-session")
    ReplayDriver()._bash("close-phase", s, script)
    assert _porcelain(s) != []  # a dirty tree: the finding F10


@pytest.mark.covers("FR-01.09/AC01")
def test_f7_a_changelog_that_disagrees_with_the_tag_is_refused_by_the_code_path_without_update_step(make_project):
    s = ss.ready_release(make_project)
    driver = CliDriver()

    def top_version_changes() -> None:  # the worktree is what `git commit -- <paths>` reads
        path = s.repo / "CHANGELOG.md"
        path.write_text(path.read_text(encoding="utf-8").replace(f"## [{VERSION}]", "## [9.9.9]", 1), encoding="utf-8", newline="\n")

    results = release_flow(driver, s, "guided", before={"commit-and-tag": top_version_changes})
    assert _steps(results)[-1] == "commit-and-tag" and results[-1].exit_code != 0
    assert f"v{VERSION}" not in s.git("tag").split()  # the refused tag is removed again, nothing was pushed
    assert "update-step" not in json.dumps(driver.log) and _remote_tags(s) == [t for t in _remote_tags(s) if VERSION not in t]


@pytest.mark.covers("FR-01.09/AC01")
def test_b1_the_release_state_names_the_release_commit_after_commit_and_tag(make_project):
    s = ss.ready_release(make_project)
    results = release_flow(CliDriver(), s, "guided")
    assert all(r.exit_code == 0 for r in results)
    record = json.loads((s.repo / ".shipwright/runtime/release_state.json").read_text(encoding="utf-8"))
    release_commit = s.git("rev-list", "-n", "1", f"v{VERSION}")
    assert (record["version"], record["tag"], record["commit"]) == (VERSION, f"v{VERSION}", release_commit)
    assert s.git("log", "-1", "--format=%s", release_commit) == f"chore(release): v{VERSION}" and "commit" in record["checks_passed"]


@pytest.mark.covers("FR-01.09/AC01")
def test_b4_the_verify_at_the_end_of_close_phase_passes_on_a_complete_release_and_fails_when_the_remote_tag_is_gone(make_project):
    s, driver, results = _standalone_flow(make_project)
    assert results[-1].step == "close-phase" and results[-1].exit_code == 0
    assert all(c["ok"] for c in driver.state["closed"]["verify"]), driver.state["closed"]["verify"]
    _remote(s, "tag", "-d", f"v{VERSION}")  # somebody deletes the tag on the host
    code, out = driver._release(s, "close-phase", "--version", VERSION, "--release-status", "skipped", "--release-note", "gh offline")
    assert code == 1 and out["status"] == "verify_failed"
    assert [c["name"] for c in out["verify"] if not c["ok"]] == ["tag_remote"]

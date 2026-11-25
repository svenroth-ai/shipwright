"""Unit P8a (F3, D7): the branch push right before ``gh pr create`` runs on real git, and a rejected push stops the release.

Old behaviour: the PR was opened before the branch was on the remote, and nothing checked the head was there. Both drivers
(replay and CLI) run the same flow on a scratch project with a bare origin and the gh stub.
"""

from __future__ import annotations

import stat
from typing import Any

import pytest

from . import scenario_support as ss
from .driver_cli import CliDriver
from .driver_replay import ReplayDriver
from .scenario_core import release_flow

DRIVERS = pytest.mark.parametrize("driver_class", [ReplayDriver, CliDriver], ids=["replay", "cli"])
pytestmark = pytest.mark.covers("FR-01.09/AC01")


def _steps(results) -> list[str]:
    return [r.step for r in results]


@DRIVERS
def test_the_head_is_on_the_remote_before_the_pr_is_opened(make_project, driver_class):
    s = ss.ready_release(make_project, pushed=False)  # a branch the remote has never seen (D7)
    seen: dict[str, str] = {}

    def look() -> None:  # runs just before `gh pr create`
        listed = s.git("ls-remote", s.origin.as_posix(), "refs/heads/release/next").split()
        seen["remote"] = listed[0] if listed else ""
        seen["local"] = s.git("rev-parse", "HEAD").strip()

    results = release_flow(driver_class(), s, "guided", before={"open-pr": look})
    steps = _steps(results)
    assert steps.index("push-branch") + 1 == steps.index("open-pr")
    assert seen["remote"] == seen["local"] != ""  # the release head was on origin when the PR was opened


@DRIVERS
def test_a_rejected_branch_push_stops_the_release_before_any_pr(make_project, driver_class):
    s = ss.ready_release(make_project)

    def close() -> None:
        hook = s.origin / "hooks" / "pre-receive"
        hook.parent.mkdir(exist_ok=True)
        hook.write_bytes(b'#!/bin/sh\necho "pre-receive: pushes are closed" >&2\nexit 1\n')
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    results = release_flow(driver_class(), s, "guided", before={"push-branch": close})
    assert _steps(results)[-1] == "push-branch" and results[-1].exit_code != 0
    assert s.gh_state()["prs"] == [] and "open-pr" not in _steps(results)
    remote_tags: Any = s.git("ls-remote", "--tags", s.origin.as_posix())
    assert "v1.3.0" not in remote_tags  # the tag stays on this machine

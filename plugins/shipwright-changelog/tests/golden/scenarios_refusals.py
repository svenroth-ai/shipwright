"""S16a-f: the ways a release stops, each with the kind of refusal it names and what it leaves behind.

Every one runs the whole release on the one configuration that can finish today (``ready_release``, guided) and
breaks exactly one thing. What no refusal may leave: a tag on the remote, an open request that claims a release,
or a recorded event of a release that did not happen. They record, not endorse, today's behaviour.
"""

from __future__ import annotations

import json
import stat
from typing import Any

from . import oracle
from . import scenario_support as ss
from .driver_replay import ReplayDriver
from .scenario_core import Run, Scenario, release_flow

A = "FR-01.09/"


def _tags(s: Any) -> list[str]:
    return s.git("tag").split()


def _remote_tags(s: Any) -> str:
    return s.git("ls-remote", "--tags", s.origin.as_posix())


def _flow(make_project, prepare=None, **flow: Any) -> Run:
    s = ss.ready_release(make_project)
    ctx = prepare(s) if prepare else {}
    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s, **flow), ctx or {})


def _stopped_at(run: Run, step: str) -> None:
    assert [r.step for r in run.results][-1] == step and run.step(step).exit_code != 0, [(r.step, r.exit_code) for r in run.results]


def _nothing_released(run: Run) -> None:
    """No tag anywhere new, no request, no release page, no event."""
    s = run.scratch
    assert _tags(s) == ["v0.1.0", "v1.2.0"] and "v1.3.0" not in _remote_tags(s)
    assert s.gh_state()["prs"] == [] and s.gh_state()["releases"] == {}
    assert run.commands("record-event-pr") == [] and run.commands("record-event-main") == []
    oracle.check_ac01(ss.notes_of(s), "v1.3.0" in _tags(s), False, outcome="stopped")


def _s16a(make_project, layout: str) -> Run:  # Step 5.4 not ok: a declared manifest of a kind that is not supported
    def declare(s: Any) -> dict:
        ss.commit(s, "pkg/package.json", '{"name": "widgets", "version": "1.2.0"}\n', "chore: a manifest")
        ss.commit(s, "shipwright_changelog_config.json", json.dumps({"published_manifests": [
            {"path": "pkg/package.json", "format": "yaml_file"}]}) + "\n", "chore: declare a manifest")
        return {}
    return _flow(make_project, declare)


def _check_s16a(run: Run) -> None:
    sync = run.step("sync")
    assert [r.step for r in run.results][-1] == "sync" and sync.output["status"] != "ok" and sync.exit_code != 0  # SKILL.md:278-280
    assert json.loads(run.commands("sync")[0]["stdout"])["status"] == sync.output["status"] == "unsupported_format"  # the kind of refusal
    assert run.commands("commit-and-tag") == []
    _nothing_released(run)


def _s16b(make_project, layout: str) -> Run:  # Step 5.5 not ok: the regenerated evidence is far smaller than the committed one
    def big_evidence(s: Any) -> dict:
        ss.commit(s, ".shipwright/compliance/sbom.md", "# SBOM\n" + "| row | of | evidence |\n" * 3000, "docs: a large evidence document")
        return {}
    return _flow(make_project, big_evidence)


def _check_s16b(run: Run) -> None:
    evidence = run.step("evidence")
    assert [r.step for r in run.results][-1] == "evidence" and evidence.output["status"] == "content_floor"  # SKILL.md:291-292: the kind of refusal
    assert json.loads(run.commands("evidence")[0]["stdout"])["status"] == "content_floor"
    assert run.commands("commit-and-tag") == [] and run.scratch.git("log", "-1", "--format=%s") == "docs: a large evidence document"
    _nothing_released(run)


def _s16c(make_project, layout: str) -> Run:  # the release audit refuses: a file nobody committed is in the tree
    def stray(s: Any) -> dict:
        (s.repo / "stray.txt").write_text("not part of the release\n", encoding="utf-8", newline="\n")
        return {}
    return _flow(make_project, stray)


def _check_s16c(run: Run) -> None:
    """D25 (operator decision 2026-11-26): a file nobody committed stops Step 6 before the commit (before: the commit was made and
    the release audit refused the dirty tree)."""
    s = run.scratch
    _stopped_at(run, "commit-and-tag")
    assert run.commands("commit-and-tag") == []  # the chain never ran
    assert s.git("log", "-1", "--format=%s") == "fix: a defect"  # no release commit
    assert "?? stray.txt" in s.git("status", "--porcelain").splitlines()  # the stray file is left as it was
    _nothing_released(run)


def _s16d(make_project, layout: str) -> Run:  # a pre-commit hook rejects the release commit
    def hook(s: Any) -> dict:
        hooks = s.stub_state / "hooks"
        hooks.mkdir()
        script = hooks / "pre-commit"
        script.write_bytes(b'#!/bin/sh\necho "pre-commit: this commit is rejected" >&2\nexit 1\n')
        script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        s.git("config", "core.hooksPath", hooks.as_posix())
        return {}
    return _flow(make_project, hook)


def _check_s16d(run: Run) -> None:
    s = run.scratch
    _stopped_at(run, "commit-and-tag")
    assert "pre-commit: this commit is rejected" in run.commands("commit-and-tag")[0]["stderr"]  # the kind of refusal
    assert s.git("log", "-1", "--format=%s") == "fix: a defect"  # no release commit
    _nothing_released(run)


def _s16e(make_project, layout: str) -> Run:  # the remote rejects every push from the event push on
    def reject() -> None:
        hook = s.origin / "hooks" / "pre-receive"
        hook.parent.mkdir(exist_ok=True)
        hook.write_bytes(b'#!/bin/sh\necho "pre-receive: pushes are closed" >&2\nexit 1\n')
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # P8a (F3): the branch is pushed before the PR now, so the remote closes after that push and before the event push,
    # the one this scenario is about (F6)
    s = ss.ready_release(make_project)
    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s, before={"record-event": reject}), {})


def _check_s16e(run: Run) -> None:
    s = run.scratch
    assert run.step("commit-and-tag").exit_code == 0 and "v1.3.0" in _tags(s)  # made here ...
    event = run.step("record-event")
    assert event.exit_code != 0 and "pre-receive: pushes are closed" in run.commands("record-event-pr")[0]["stderr"]  # the kind of refusal
    # F6 (operator 2026-11-23): the `&&` chain of SKILL.md:341 stops the release at the rejected push: no tag push, no page
    assert [r.step for r in run.results][-1] == "record-event" and "v1.3.0" not in _remote_tags(s)  # ... and nowhere else
    assert s.gh_state()["releases"] == {} and not {"push-tags", "release-page"} & {r.step for r in run.results}
    assert s.git("log", "-1", "--format=%s") == "chore(release): record changelog event for v1.3.0"  # the event is local only
    oracle.check_ac01(ss.notes_of(s), True, request_open=bool(s.gh_state()["prs"]), outcome="prepared")  # a request exists, nothing is out there


def _s16f(make_project, layout: str) -> Run:  # gh is not installed: no seam points at a program that exists
    def gh_missing() -> None:
        s.env["SHIPWRIGHT_TEST_GH_ARGV_PREFIX"] = json.dumps(["gh-is-not-installed-here"])

    s = ss.ready_release(make_project)
    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s, before={"open-pr": gh_missing}), {})


def _check_s16f(run: Run) -> None:
    s = run.scratch
    pr = run.step("open-pr")
    assert pr.exit_code == 127 and pr.output["status"] == "failed"  # the program could not be started (the OS words its message)
    # F4 (operator 2026-11-23): a request that cannot be opened stops the release before anything is pushed or published
    assert [r.step for r in run.results][-1] == "open-pr" and not {"push-tags", "release-page"} & {r.step for r in run.results}
    assert s.gh_state()["prs"] == [] and "v1.3.0" in _tags(s) and "v1.3.0" not in _remote_tags(s)  # the tag stays on this machine
    oracle.check_ac01(ss.notes_of(s), True, request_open=False, outcome="no_request")  # AC01: two of three, said so by the exit code


SCENARIOS = {
    "S16a": Scenario("S16a", ("legacy",), _s16a, _check_s16a, acs=(f"{A}AC01",)),
    "S16b": Scenario("S16b", ("legacy",), _s16b, _check_s16b, acs=(f"{A}AC01",)),
    "S16c": Scenario("S16c", ("legacy",), _s16c, _check_s16c, acs=(f"{A}AC01",)),
    "S16d": Scenario("S16d", ("legacy",), _s16d, _check_s16d, acs=(f"{A}AC01",)),
    "S16e": Scenario("S16e", ("legacy",), _s16e, _check_s16e, acs=(f"{A}AC01",)),
    "S16f": Scenario("S16f", ("legacy",), _s16f, _check_s16f, acs=(f"{A}AC01",)),
}

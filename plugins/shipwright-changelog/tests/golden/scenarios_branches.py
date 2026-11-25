"""S14a/b/c/d and S15: where the release is made from, and what Step 6 may commit.

S14 runs the whole release (guided, the one configuration that can finish today: ``scenario_support.ready_release``)
from a branch the remote has never seen, from ``main`` and from a repository whose default branch is ``master``.
Since P8a (operator 2026-11-25) they assert the fixes, not the findings: F3 for D7 (the head is pushed right before the
request is opened, so the host accepts it) and F5 for D24 (the default branch is read from the remote: on a ``master``
repository the release is cut on ``master`` as the trunk, with no request, and ``master`` and the tag reach the remote).
``_s14d`` (P8a fix round, D85): the default branch is ``develop`` and the release is cut on ``main``, which stays a trunk. It is run by
``test_p8a_fix_scenarios.py`` through both drivers, not registered here: a new frozen trace would need a re-pin of the golden lock.
"""

from __future__ import annotations

from typing import Any

from . import oracle
from . import scenario_support as ss
from .driver_replay import ReplayDriver
from .scenario_core import Run, Scenario, release_flow

A = "FR-01.09/"


def _tag_made(s: Any, version: str = "1.3.0") -> bool:
    return f"v{version}" in s.git("tag").split()


def _on_origin(s: Any, ref: str) -> bool:
    return bool(s.run(["git", "--git-dir", s.origin.as_posix(), "rev-parse", "--verify", "-q", ref]).stdout.strip())


def _flow(make_project, **ready: Any) -> Run:
    s = ss.ready_release(make_project, **ready)
    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s), {})


def _s14a(make_project, layout: str) -> Run:
    return _flow(make_project, branch="release/fresh", pushed=False)


def _check_s14a(run: Run) -> None:
    s = run.scratch
    steps = [r.step for r in run.results]
    # F3 (D7): the branch the remote has never seen is pushed first, then the request opens against the default branch
    assert steps.index("push-branch") + 1 == steps.index("open-pr") and run.step("push-branch").exit_code == 0
    assert run.step("open-pr").exit_code == 0 and _on_origin(s, "refs/heads/release/fresh")
    (pr,) = s.gh_state()["prs"]
    assert (pr["head"], pr["base"], pr["state"]) == ("release/fresh", "main", "open")
    # F1b: a guided release then waits for the merge: the event is recorded and pushed, the tag stays on this machine
    assert steps[-1] == "record-event" and run.step("record-event").exit_code == 0
    assert not _on_origin(s, "refs/tags/v1.3.0") and _tag_made(s)
    oracle.check_tag_on_release_commit(s.git("log", "-1", "--format=%s", "v1.3.0"), "1.3.0")
    is_open = any(p["state"] == "open" for p in s.gh_state()["prs"])
    oracle.check_ac01(ss.notes_of(s), _tag_made(s), request_open=is_open, outcome="prepared")  # AC01: note, tag, an open request
    oracle.check_ac11_not_published(s.gh_state(), tag_on_remote=_on_origin(s, "refs/tags/v1.3.0"), pr_open=is_open)  # AC11: nothing out yet


def _s14b(make_project, layout: str) -> Run:
    return _flow(make_project, branch=None)


def _check_s14b(run: Run) -> None:
    s = run.scratch
    assert all(r.exit_code == 0 for r in run.results) and "open-pr" not in [r.step for r in run.results]  # SKILL.md:327-356
    assert run.commands("record-event-main") and not run.commands("open-pr") and run.gh_calls("pr") == []
    assert s.git("rev-parse", "main") == s.git("--git-dir", s.origin.as_posix(), "rev-parse", "main")  # tag, release and event pushed
    oracle.check_tag_on_release_commit(s.git("log", "-1", "--format=%s", "v1.3.0"), "1.3.0")
    oracle.check_ac01(ss.notes_of(s), _tag_made(s), request_open=False, outcome="no_request")  # AC01: on main there is no request
    oracle.check_ac11_not_published(s.gh_state(), tag_on_remote=_on_origin(s, "refs/tags/v1.3.0"), pr_open=any(p["state"] == "open" for p in s.gh_state()["prs"]))


def _s14c(make_project, layout: str) -> Run:
    # a clone knows its remote's default branch as origin/HEAD; the scratch's fetch URL is a fake host, so it is set here
    return _flow(make_project, branch=None, default_branch="master", setup=lambda s: s.git("remote", "set-head", "origin", "master"))


def _check_s14c(run: Run) -> None:
    s = run.scratch
    # F5 (D24): `master` is the remote's default branch, so it is the trunk: no request, the release completes on it
    assert s.git("rev-parse", "--abbrev-ref", "HEAD") == "master" and all(r.exit_code == 0 for r in run.results)
    assert not run.commands("open-pr") and not run.commands("push-branch") and run.gh_calls("pr") == [] and run.commands("record-event-main")
    assert s.git("rev-parse", "master") == s.git("--git-dir", s.origin.as_posix(), "rev-parse", "master")  # the release reached the remote
    assert _on_origin(s, "refs/tags/v1.3.0") and not _on_origin(s, "refs/heads/main")
    oracle.check_tag_on_release_commit(s.git("log", "-1", "--format=%s", "v1.3.0"), "1.3.0")
    oracle.check_ac01(ss.notes_of(s), _tag_made(s), request_open=False, outcome="no_request")  # AC01: on the trunk there is no request
    oracle.check_ac11_not_published(s.gh_state(), tag_on_remote=_on_origin(s, "refs/tags/v1.3.0"), pr_open=False)


def _develop_default(s: Any) -> None:
    """The remote's default branch is ``develop`` (pushed, HEAD of the bare remote and the local origin/HEAD); work stays on ``main``."""
    s.git("branch", "develop")
    s.git("push", "-q", "origin", "develop")
    s.run(["git", "--git-dir", s.origin.as_posix(), "symbolic-ref", "HEAD", "refs/heads/develop"], check=True)
    s.git("remote", "set-head", "origin", "develop")


def _s14d(make_project, layout: str) -> Run:
    return _flow(make_project, branch=None, setup=_develop_default)


def _check_s14d(run: Run) -> None:
    s = run.scratch
    # P8a fix round (D85): the trunks are additive. `develop` is the default branch, and `main` stays a trunk: no head push, no request
    assert s.git("rev-parse", "--abbrev-ref", "HEAD") == "main" and run.driver.trunk(s) == "develop"
    assert all(r.exit_code == 0 for r in run.results) and not run.commands("push-branch") and not run.commands("open-pr")
    assert run.gh_calls("pr") == [] and run.commands("record-event-main")
    assert s.git("rev-parse", "main") == s.git("--git-dir", s.origin.as_posix(), "rev-parse", "main")  # main went out with the tag
    assert _on_origin(s, "refs/tags/v1.3.0") and s.git("rev-parse", "develop") != s.git("rev-parse", "main")
    oracle.check_tag_on_release_commit(s.git("log", "-1", "--format=%s", "v1.3.0"), "1.3.0")
    oracle.check_ac01(ss.notes_of(s), _tag_made(s), request_open=False, outcome="no_request")  # AC01: on a trunk there is no request
    oracle.check_ac11_not_published(s.gh_state(), tag_on_remote=_on_origin(s, "refs/tags/v1.3.0"), pr_open=False)


def _s15(make_project, layout: str) -> Run:
    s = ss.ready_release(make_project)
    ss.commit(s, "notes.txt", "one\n", "docs: notes")
    (s.repo / "notes.txt").write_text("two\n", encoding="utf-8", newline="\n")  # an unrelated change, not staged
    (s.repo / "staged.txt").write_text("a person was in the middle of this\n", encoding="utf-8", newline="\n")
    s.git("add", "--", "staged.txt")  # an unrelated file, staged
    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s), {"unrelated": ["notes.txt", "staged.txt"]})


def _check_s15(run: Run) -> None:
    s = run.scratch
    done = run.step("commit-and-tag")
    assert s.git("log", "-1", "--format=%s") == "chore(release): v1.3.0"  # the commit was made ...
    changed = s.git("show", "--name-only", "--format=", "HEAD").splitlines()
    oracle.check_release_commit_paths(changed, run.ctx["unrelated"])  # Step 6: by explicit pathspec, nothing else goes in
    status = s.run(["git", "status", "--porcelain"]).stdout.splitlines()
    assert [ln for ln in status if "txt" in ln] == [" M notes.txt", "A  staged.txt"], status  # both are still the person's
    # ... but the release audit refuses the tree that these two leave dirty: no tag, as in S1t (today's behaviour)
    assert done.exit_code != 0 and "release audit refuses a dirty working tree" in run.commands("commit-and-tag")[0]["stderr"]
    assert not _tag_made(s) and run.gh_calls("pr") == []


SCENARIOS = {
    "S14a": Scenario("S14a", ("legacy",), _s14a, _check_s14a, acs=(f"{A}AC01", f"{A}AC11")),
    "S14b": Scenario("S14b", ("legacy",), _s14b, _check_s14b, acs=(f"{A}AC01", f"{A}AC11")),
    "S14c": Scenario("S14c", ("legacy",), _s14c, _check_s14c, acs=(f"{A}AC01", f"{A}AC11")),
    "S15": Scenario("S15", ("legacy",), _s15, _check_s15),
}

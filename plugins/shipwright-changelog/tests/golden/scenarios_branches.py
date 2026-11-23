"""S14a/b/c and S15: where the release is made from, and what Step 6 may commit.

S14 runs the whole release (guided, the one configuration that can finish today: ``scenario_support.ready_release``)
from a branch the remote has never seen, from ``main`` and from a repository whose default branch is ``master``.
They record, not endorse: D7 (the request is opened before the head is pushed, and ``git push --tags origin main``
pushes whatever local ``main`` holds) and D24 (new: SKILL.md:327 knows ``main`` and ``develop`` only, so on a
``master`` repository the skill opens a request against a ``main`` that does not exist and pushes a ``main`` that
does not exist).
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
    pr = run.step("open-pr")
    # D7: `gh pr create` (SKILL.md:333) runs before `git push origin HEAD` (:349), so the host refuses the request
    assert pr.exit_code != 0 and "is not on the remote" in run.commands("open-pr")[0]["stderr"], run.commands("open-pr")[0]
    assert s.gh_state()["prs"] == []
    # F4 (operator 2026-11-23): no request, no release. The flow stops here: the head was never pushed, no event was
    # recorded and the tag exists on this machine only
    assert [r.step for r in run.results][-1] == "open-pr" and not _on_origin(s, "refs/heads/release/fresh")
    assert not _on_origin(s, "refs/tags/v1.3.0") and _tag_made(s) and run.commands("record-event-pr") == []
    oracle.check_tag_on_release_commit(s.git("log", "-1", "--format=%s", "v1.3.0"), "1.3.0")
    oracle.check_ac01(ss.notes_of(s), _tag_made(s), request_open=False, outcome="no_request")  # AC01: no request was opened
    oracle.check_ac11_not_published(s.gh_state(), tag_on_remote=_on_origin(s, "refs/tags/v1.3.0"), pr_open=any(p["state"] == "open" for p in s.gh_state()["prs"]))  # AC11: no request, so no breach


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
    return _flow(make_project, branch=None, default_branch="master")


def _check_s14c(run: Run) -> None:
    s = run.scratch
    assert s.git("rev-parse", "--abbrev-ref", "HEAD") == "master" and run.commands("open-pr")  # D24: master is a "feature branch"
    pr = run.step("open-pr")
    assert pr.exit_code != 0 and "base branch 'main' is not on the remote" in run.commands("open-pr")[0]["stderr"]
    # F4 (operator 2026-11-23): the refused request stops the release; nothing is pushed and the tag stays on this machine
    assert [r.step for r in run.results][-1] == "open-pr" and not _on_origin(s, "refs/tags/v1.3.0")
    oracle.check_ac01(ss.notes_of(s), _tag_made(s), request_open=False, outcome="no_request")  # AC01: tag only on this machine
    oracle.check_ac11_not_published(s.gh_state(), tag_on_remote=_on_origin(s, "refs/tags/v1.3.0"), pr_open=any(p["state"] == "open" for p in s.gh_state()["prs"]))


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

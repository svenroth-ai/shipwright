"""S3, S3b, S4, S5a, S5b: which version is proposed, and when a release stops before it starts.

None of these touches the events layout, so each has one trace. They record, not endorse, today's behaviour:
D5 (S3b): the proposed version comes from commit messages only, so a break recorded in a drop alone gives a patch.
D17 (S5a, S5b): "nothing to release" stops at two different places with two different messages.
"""

from __future__ import annotations

from . import oracle
from . import scenario_support as ss
from .driver_replay import ReplayDriver
from .scenario_core import Run, Scenario, release_flow


def messages_since(scratch, tag: str) -> list[str]:
    """The commit messages after ``tag``, straight from git (the oracle must not ask the tool under test)."""
    raw = scratch.git("log", f"{tag}..HEAD", "--format=%B%x00")
    return [m.strip() for m in raw.split("\x00") if m.strip()]


def _prepared(make_project, *, tag: str | None, commits: list[tuple[str, str, str]], drops=()) -> Run:
    s = make_project(tagged=tag is not None)
    if tag and tag != "v0.1.0":
        ss.tag(s, tag)
    ss.feature_branch(s, "work/next")
    for path, text, message in commits:
        ss.commit(s, path, text, message)
    for category, bullet in drops:
        ss.write_drop(s, category, bullet)
    driver = ReplayDriver()
    results = [driver.run_step("prepare", s)]
    return Run(s, driver, results, {"tag": tag, "messages": messages_since(s, tag) if tag else [], "drops": len(drops)})


def _s3(make_project, layout: str) -> Run:
    return _prepared(make_project, tag="v0.1.0", commits=[("api.txt", "1\n", "feat!: rename the public option"),
                                                          ("fix.txt", "2\n", "fix: a defect")])


def _check_s3(run: Run) -> None:
    out = run.step("prepare").output
    oracle.check_ac04_version(out["version"], "v0.1.0", run.ctx["messages"])  # a break before 1.0 raises the SECOND number
    assert out["version"] == "0.2.0" and out["version_reason"] == "breaking change (pre-1.0)"


def _s3b(make_project, layout: str) -> Run:
    return _prepared(make_project, tag="v0.1.0", commits=[("fix.txt", "1\n", "fix: a defect")],
                     drops=[("Changed", "**BREAKING** the old option is removed")])


def _check_s3b(run: Run) -> None:
    out = run.step("prepare").output
    messages = run.ctx["messages"]
    # D5: the proposal ignores the drop, so it is the patch bump the commits alone give ...
    oracle.check_ac04_version(out["version"], "v0.1.0", messages)
    assert out["version"] == "0.1.1"
    # ... whereas AC04 over what is recorded since the last release (the drop is a recorded break) gives 0.2.0
    assert oracle.expected_version("v0.1.0", messages, breaking_drops=run.ctx["drops"]) == "0.2.0" != out["version"]


def _s4(make_project, layout: str) -> Run:
    return _prepared(make_project, tag="v1.2.0",
                     commits=[("api.txt", "1\n", "feat(api)!: drop the v1 endpoints"),
                              ("db.txt", "2\n", "fix: migrate\n\nBREAKING CHANGE: the table is renamed"),
                              ("more.txt", "3\n", "feat: a new capability")])


def _check_s4(run: Run) -> None:
    out = run.step("prepare").output
    oracle.check_ac04_version(out["version"], "v1.2.0", run.ctx["messages"])  # a break after 1.0 raises the FIRST number
    assert out["version"] == "2.0.0" and out["version_reason"] == "breaking change"


def _s5a(make_project, layout: str) -> Run:
    s = make_project()
    ss.tag(s, "v0.2.0")  # HEAD is already released
    before = s.git("rev-parse", "HEAD")
    ctx = {"head": before, "after": ss.digest(s)}  # taken before the flow: "after" is what must still be true after it
    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s), ctx)


def _check_s5a(run: Run) -> None:
    s = run.scratch
    out = run.step("prepare").output
    assert (out["status"], out["reason"], out["commits_since_tag"]) == ("stop", "no_unreleased_changes", 0)  # AC03: says so, stops
    assert [r.step for r in run.results] == ["prepare"] and run.commands("aggregate") == []
    assert s.git("rev-parse", "HEAD") == run.ctx["head"] and s.git("status", "--porcelain") == ""
    assert ss.digest(s) == run.ctx["after"] and run.gh_calls("pr") == []


def _s5b(make_project, layout: str) -> Run:
    s = make_project()
    ss.feature_branch(s, "work/next")
    ss.commit(s, "api.txt", "1\n", "feat: something that was never recorded as a drop")
    ctx = {"head": s.git("rev-parse", "HEAD"), "after": ss.digest(s)}
    driver = ReplayDriver()
    return Run(s, driver, release_flow(driver, s), ctx)


def _check_s5b(run: Run) -> None:
    s = run.scratch
    assert run.step("prepare").output["status"] == "ok"
    refused = run.step("aggregate", 1)  # the dry run (0) previews an empty section; the real call refuses
    assert refused.exit_code == 1 and refused.output["status"] == "failed"
    stderr = run.commands("aggregate")[0]["stderr"]
    assert "nothing to release" in stderr and "empty release" in stderr, stderr  # AC03: says so and refuses
    assert [r.step for r in run.results][-1] == "aggregate" and s.git("rev-parse", "HEAD") == run.ctx["head"]
    assert s.git("tag").split() == ["v0.1.0"] and ss.digest(s) == run.ctx["after"]  # nothing written, nothing tagged


SCENARIOS = {
    "S3": Scenario("S3", ("drops",), _s3, _check_s3),
    "S3b": Scenario("S3b", ("drops",), _s3b, _check_s3b),
    "S4": Scenario("S4", ("drops",), _s4, _check_s4),
    "S5a": Scenario("S5a", ("drops",), _s5a, _check_s5a),
    "S5b": Scenario("S5b", ("drops",), _s5b, _check_s5b),
}

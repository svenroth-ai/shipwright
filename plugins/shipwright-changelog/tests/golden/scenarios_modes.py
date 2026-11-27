"""S13, S17a/b, S18a/b/c, S19: a dispatched run, the two ways the mode check speaks, the preview, and ``--from``.

S13 drives the REAL orchestrator (``write-config``, ``single-session-next`` and ``-apply``) through the phases before
the changelog, runs the release the way a dispatched phase-runner would (token handed in, the phase-complete block at
the end) and hands the result to ``single-session-apply`` with the phase gate on. They record, not endorse, today's
behaviour: D2 (a driven run leaves the request open AND has pushed the tag). S19 no longer records D9: since P8b (Q7, operator
2026-11-25) ``--from`` is offered nowhere, and passing it anyway is refused as an unknown argument with nothing changed. S18a/b no longer record D12: since P8a (F2, operator 2026-11-25) the preview is the dry run and the real aggregation
runs only after Accept, so Cancel leaves the tree and the drops byte-identical and Edit changes the drop and repeats the dry run.
S18c (P8a fix round, D84; ``_s18(True, "cancel")``): an Edit then Cancel; ``release.py cancel`` puts the edited drop back, so the tree is as
before. Frozen since the stop-3 re-pin (D107).
"""

from __future__ import annotations

import json
from typing import Any

import minimal_valid_project as mvp

from . import oracle
from . import scenario_support as ss
from .driver_replay import ReplayDriver
from .replay_commands import PLUGIN
from .scenario_core import Run, Scenario, release_flow

A = "FR-01.09/"
# what a dispatched run's own set-up commits: ids and uuids of the run, the plans the phases wrote
RUN_FILES = ("shipwright_run_config.json", ".shipwright/run_loop*", ".shipwright/planning/*")


def _s13(make_project, layout: str) -> Run:
    box: dict[str, Any] = {}
    s = ss.ready_release(make_project, tagged=False, setup=lambda scratch: box.update(dispatch=ss.drive_to_changelog(scratch)))
    dispatch = box["dispatch"]
    driver = ReplayDriver()
    results = release_flow(driver, s, "guided", pipeline=True, close=True, phase_task_id=dispatch["phaseTaskId"])
    ctx: dict[str, Any] = {}
    if results[-1].step == "close-phase":  # the master applies the phase-runner's result with the gate on
        ctx["applied"] = ss.apply_phase(s, dispatch, ["CHANGELOG.md"])
    return Run(s, driver, results, ctx, judgement=RUN_FILES)


def _check_s13(run: Run) -> None:
    s, out = run.scratch, run.step("prepare").output
    assert all(r.exit_code == 0 for r in run.results), [(r.step, r.exit_code) for r in run.results]
    # truth table, pipeline x guided: the version is auto-accepted, the preview is skipped, the request stays open
    assert out["mode"] == "pipeline" and out["version_question"] == "auto-accepted", out
    assert "preview" not in [r.step for r in run.results] and run.gh_calls("pr", "merge") == []
    prs = s.gh_state()["prs"]
    assert [p["state"] for p in prs] == ["open"] and "v1.3.0" in s.git("tag").split()
    oracle.check_tag_on_release_commit(s.git("log", "-1", "--format=%s", "v1.3.0"), "1.3.0")
    oracle.check_ac01(ss.notes_of(s), True, request_open=True, outcome="prepared")  # AC01: note, tag and an open request
    oracle.expect_ac11_violated_today(s.gh_state(), "refs/tags/v1.3.0" in s.git("ls-remote", "--tags", s.origin.as_posix()),
                                      pr_open=True)  # AC11 / D2: out while the request is open
    applied = run.ctx["applied"]  # `_validate_changelog` (tag exists, changelog matches the tag) and the phase_history run id
    assert applied["ok"] is True and applied["gate"]["result"] == "pass", applied
    history = json.loads((s.repo / "shipwright_run_config.json").read_text(encoding="utf-8"))["phase_history"]["changelog"]
    assert history[-1]["run_id"].startswith("changelog-v1.3.0-") and history[-1]["outcome"] == "tagged"


def _s17a(make_project, layout: str) -> Run:
    s = make_project(events_layout="legacy", tagged=False)
    dispatch = ss.start_run(s)
    ss.apply_phase(s, dispatch, mvp.write_phase(s.repo, "project"))  # the project task is done: its token is spent
    driver = ReplayDriver()
    before = ss.digest(s)
    return Run(s, driver, [driver.run_step("prepare", s, phase_task_id=dispatch["phaseTaskId"])], {"before": before})


def _check_s17a(run: Run) -> None:
    out = run.step("prepare").output
    # SKILL.md:67-70: a token that does not resolve is `error`: STOP, never carry on as a standalone run
    assert (out["status"], out["reason"], out["mode"]) == ("stop", "mode_error", "error") and run.step("prepare").exit_code == 2
    assert [c["key"] for c in run.driver.log] == ["context"] and ss.digest(run.scratch) == run.ctx["before"]


def _s17b(make_project, layout: str) -> Run:
    s = ss.ready_release(make_project, tagged=False, setup=ss.start_run)  # a driven run is live at the project phase
    driver = ReplayDriver()
    return Run(s, driver, [driver.run_step("prepare", s)], {}, judgement=RUN_FILES)


def _check_s17b(run: Run) -> None:
    out = run.step("prepare").output
    assert out["mode"] == "standalone" and out["out_of_sequence"] == "asked", out  # SKILL.md:63-66: warn, ask before going on
    context = json.loads(run.commands("context")[0]["stdout"])
    assert context["requires_out_of_sequence_warning"] is True and context["active_phases"] == ["project"]


def _s18(edit: bool, then: str = "accept"):
    """F2 (operator 2026-11-25, P8a; D12): the preview is the dry run, asked BEFORE the real aggregation writes anything.
    ``then``: what the operator answers after an Edit (S18b Accept, S18c Cancel: ``release.py cancel`` puts the drop back, D84)."""
    def run(make_project, layout: str) -> Run:
        s = ss.ready_release(make_project)
        driver = ReplayDriver()
        ctx = {"before": ss.digest(s)}
        results = [driver.run_step("prepare", s)]
        version = results[0].output["version"]
        results.append(driver.run_step("aggregate", s, version=version, dry_run=True))
        ctx["previewed"] = ss.digest(s)
        results.append(driver.run_step("preview", s, choice="edit" if edit else "cancel"))
        if edit:  # Edit changes the pending entry the text comes from, then the dry run and the question repeat
            drop = next(p for p in (s.repo / "CHANGELOG-unreleased.d").rglob("*.md")
                        if "A new capability readers can use" in p.read_text(encoding="utf-8"))
            drop.write_text(drop.read_text(encoding="utf-8").replace("A new capability readers can use", "A new capability, reworded"),
                            encoding="utf-8", newline="\n")
            ctx["edited"] = ss.digest(s)
            results.append(driver.run_step("aggregate", s, version=version, dry_run=True))
            ctx["repreviewed"] = ss.digest(s)
            results.append(driver.run_step("preview", s, choice=then))
            if then == "accept":
                results.append(driver.run_step("aggregate", s, version=version))  # Accept: the one real write
        return Run(s, driver, results, ctx)
    return run


def _check_s18(edit: bool, then: str = "accept"):
    def check(run: Run) -> None:
        s, ctx = run.scratch, run.ctx
        shown = run.commands("aggregate-dry")[0]["stdout"]
        oracle.check_ac10_unchanged(ctx["before"], ctx["previewed"], shown, ["A new capability readers can use"])  # AC10: shown, nothing written
        assert not [t for t in s.git("tag").split() if t == "v1.3.0"] and s.git("log", "-1", "--format=%s") == "fix: a defect"
        if not edit or then == "cancel":  # Cancel: the tree and the pending drops are byte-identical to before the release started
            assert [r.step for r in run.results][-1] == "preview" and run.step("preview", -1).output["status"] == "cancel"
            assert ss.digest(s) == ctx["before"] and run.commands("aggregate") == [] and run.step("preview", -1).exit_code == 0
            if edit:  # S18c: the Edit really changed the drop, and the second preview showed it, before Cancel put it back
                assert ctx["edited"] != ctx["before"] and "A new capability, reworded" in run.commands("aggregate-dry")[1]["stdout"]
            return
        assert [run.step("preview", n).output["status"] for n in (0, 1)] == ["edit", "accept"]
        assert ctx["repreviewed"] == ctx["edited"] and "A new capability, reworded" in run.commands("aggregate-dry")[1]["stdout"]
        assert run.step("aggregate", 2).exit_code == 0 and run.step("aggregate", 2).output["changelog_updated"] is True
        assert "A new capability, reworded" in ss.notes_of(s) and "readers can use" not in ss.notes_of(s)
        oracle.check_drops_consumed([p.name for p in (s.repo / "CHANGELOG-unreleased.d").rglob("*.md")])  # only the real run uses them
    return check


def _s19(make_project, layout: str) -> Run:
    driver = ReplayDriver()
    s = ss.ready_release(make_project)
    before = ss.digest(s)  # taken BEFORE the refused command runs, or an unchanged-disk check proves nothing
    return Run(s, driver, [driver.run_step("prepare", s, from_version="v0.1.0")], {"before": before})


def _check_s19(run: Run) -> None:
    out = run.step("prepare").output
    # Q7 (D9): the live skill offers no `--from`; passed anyway, it is an unknown argument and nothing changes
    assert "--from" not in (PLUGIN / "skills" / "changelog" / "SKILL.md").read_text(encoding="utf-8")
    assert (out["status"], out["reason"]) == ("failed", "exit_2") and run.step("prepare").exit_code == 2
    said = "".join(c["stderr"] for c in run.driver.log)
    assert "unrecognized arguments: --from" in said and ss.digest(run.scratch) == run.ctx["before"]


SCENARIOS = {
    "S13": Scenario("S13", ("legacy",), _s13, _check_s13, acs=(f"{A}AC01", f"{A}AC11")),
    "S17a": Scenario("S17a", ("legacy",), _s17a, _check_s17a),
    "S17b": Scenario("S17b", ("legacy",), _s17b, _check_s17b),
    "S18a": Scenario("S18a", ("legacy",), _s18(False), _check_s18(False), acs=(f"{A}AC10",)),
    "S18b": Scenario("S18b", ("legacy",), _s18(True), _check_s18(True), acs=(f"{A}AC10",)),
    "S18c": Scenario("S18c", ("legacy",), _s18(True, "cancel"), _check_s18(True, "cancel"), acs=(f"{A}AC10",)),
    "S19": Scenario("S19", ("legacy",), _s19, _check_s19),
}

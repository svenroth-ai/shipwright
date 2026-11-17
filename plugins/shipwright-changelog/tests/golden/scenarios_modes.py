"""S13, S17a/b, S18a/b, S19: a dispatched run, the two ways the mode check speaks, the preview, and ``--from``.

S13 drives the REAL orchestrator (``write-config``, ``single-session-next`` and ``-apply``) through the phases before
the changelog, runs the release the way a dispatched phase-runner would (token handed in, the phase-complete block at
the end) and hands the result to ``single-session-apply`` with the phase gate on. They record, not endorse, today's
behaviour: D2 (a driven run leaves the request open AND has pushed the tag), D12 (the preview is shown after the
aggregation has written the changelog and used up the drops) and D9 (``--from`` is advertised and implemented nowhere).
"""

from __future__ import annotations

import json
from typing import Any

import minimal_valid_project as mvp

from . import oracle
from . import scenario_support as ss
from .driver_replay import ReplayDriver
from .replay_commands import SKILL
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


def _s18(edit: bool):
    def run(make_project, layout: str) -> Run:
        s = ss.ready_release(make_project)
        driver = ReplayDriver()
        ctx = {"before": ss.digest(s)}
        results = [driver.run_step("prepare", s)]
        version = results[0].output["version"]
        results.append(driver.run_step("aggregate", s, version=version, dry_run=True))
        results.append(driver.run_step("aggregate", s, version=version))  # today's order: the real write comes BEFORE the preview
        ctx["written"] = ss.digest(s)
        results.append(driver.run_step("preview", s, choice="edit" if edit else "cancel"))
        if edit:  # "apply the described changes and re-preview": the person edits the section by hand
            text = (s.repo / "CHANGELOG.md").read_text(encoding="utf-8")
            (s.repo / "CHANGELOG.md").write_text(text.replace("A new capability readers can use", "A new capability, reworded"),
                                                 encoding="utf-8", newline="\n")
            results.append(driver.run_step("aggregate", s, version=version, dry_run=True))
            ctx["edited"] = ss.digest(s)
            results.append(driver.run_step("preview", s, choice="accept"))
        return Run(s, driver, results, ctx)
    return run


def _check_s18(edit: bool):
    def check(run: Run) -> None:
        s, ctx = run.scratch, run.ctx
        assert ctx["written"] != ctx["before"]  # D12: by the time the preview is shown, CHANGELOG.md is written ...
        left = [p.name for p in (s.repo / "CHANGELOG-unreleased.d").rglob("*.md")]
        oracle.check_drops_consumed(left)  # ... and the pending entries are used up
        assert not [t for t in s.git("tag").split() if t == "v1.3.0"] and s.git("log", "-1", "--format=%s") == "fix: a defect"
        if not edit:  # cancel puts nothing back (the question of the operator's decision 4: today's behaviour is recorded)
            assert [r.step for r in run.results][-1] == "preview" and run.step("preview").output["status"] == "cancel"
            assert ss.digest(s) == ctx["written"]
            return
        assert [run.step("preview", n).output["status"] for n in (0, 1)] == ["edit", "accept"]
        assert run.step("aggregate", 2).exit_code == 0 and run.step("aggregate", 2).output["changelog_updated"] is False
        text = (s.repo / "CHANGELOG.md").read_text(encoding="utf-8")
        assert "A new capability, reworded" in text and ss.digest(s) == ctx["edited"]  # the re-preview does not undo the edit
    return check


def _s19(make_project, layout: str) -> Run:
    driver = ReplayDriver()
    s = ss.ready_release(make_project)
    before = ss.digest(s)  # taken BEFORE the refused command runs, or an unchanged-disk check proves nothing
    return Run(s, driver, [driver.run_step("prepare", s, from_version="v0.1.0")], {"before": before})


def _check_s19(run: Run) -> None:
    out = run.step("prepare").output
    # D9: the banner advertises `--from v0.1.0` (SKILL.md:26); the setup script has no such argument and refuses it
    assert "--from v0.1.0" in SKILL.read_text(encoding="utf-8").splitlines()[25]
    assert (out["status"], out["reason"]) == ("stop", "setup_refused") and run.step("prepare").exit_code != 0
    assert "unrecognized arguments: --from" in run.commands("setup")[0]["stderr"] and ss.digest(run.scratch) == run.ctx["before"]


SCENARIOS = {
    "S13": Scenario("S13", ("legacy",), _s13, _check_s13, acs=(f"{A}AC01", f"{A}AC11")),
    "S17a": Scenario("S17a", ("legacy",), _s17a, _check_s17a),
    "S17b": Scenario("S17b", ("legacy",), _s17b, _check_s17b),
    "S18a": Scenario("S18a", ("legacy",), _s18(False), _check_s18(False)),
    "S18b": Scenario("S18b", ("legacy",), _s18(True), _check_s18(True)),
    "S19": Scenario("S19", ("legacy",), _s19, _check_s19),
}

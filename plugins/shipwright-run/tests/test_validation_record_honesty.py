"""The override record must not assert things the gate did not establish.

Reproductions for defects a Stage-2 code review and a Stage-3 doubt review found
in `iterate-2026-07-27-phase-gate-override-evidence` (merged f6179f6e). The
record is the one artifact whose whole purpose is being trustworthy afterwards;
each test below pins a way it was not.

Root causes R3, R4, R8, R9, R10, R11 in
`.shipwright/planning/iterate/iterate-2026-07-27-handoff-tally-and-gate-honesty.md`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config, load_run_config, update_step  # noqa: E402
from orchestrator_pkg.validation_record import (  # noqa: E402
    GATE_ERROR_PREFIX,
    VALIDATION_OVERRIDES_KEY,
    run_phase_gate,
)

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "lib" / "orchestrator.py")
REASON = "shipping tonight; tracked in #123"
ASK = {"severity": "ask", "message": "Missing spec.md for splits: 01-core"}
INFORM = {"severity": "inform", "message": "E2E flakiness noted"}


@pytest.fixture
def run_project(tmp_project, mocker):
    """A non-standalone run the v1 completion path can advance (mode stripped —
    `update-step` is inert in a driven single_session run)."""
    mocker.patch("orchestrator.run_compliance_update", return_value=None)
    create_config(
        scope="full_app", profile="supabase-nextjs", autonomy="guided",
        deploy_target="jelastic-dev", project_root=tmp_project,
    )
    path = tmp_project / "shipwright_run_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    del config["mode"]
    path.write_text(json.dumps(config), encoding="utf-8")
    return tmp_project


def _gate(mocker, *issues):
    return mocker.patch(
        "phase_validators.validate_phase",
        return_value=(not any(i["severity"] == "ask" for i in issues), list(issues)),
    )


def _overrides(project_root):
    return load_run_config(project_root).get(VALIDATION_OVERRIDES_KEY, [])


# --------------------------------------------------------------------------- #
# R3 — a forced retry left the pause marker behind
# --------------------------------------------------------------------------- #

def test_a_forced_retry_clears_the_needs_validation_status(run_project, mocker):
    """The predecessor popped `validation_issues` but never reset `status`, so a
    completed step still reported itself as awaiting a decision. Its own comment
    claimed otherwise, and its test stopped one assertion short."""
    gate = _gate(mocker, ASK)
    paused = update_step(run_project, "project", "complete")
    assert paused["status"] == "needs_validation"

    gate.return_value = (True, [])
    config = update_step(run_project, "project", "complete", force=True, force_reason=REASON)

    assert config["status"] != "needs_validation"
    assert config["status"] == "in_progress"
    assert "validation_issues" not in config
    assert "project" in config["completed_steps"]


def test_the_pipeline_complete_status_still_wins(run_project, mocker):
    """Clearing the pause must not stomp the terminal assignment."""
    _gate(mocker)
    for step in load_run_config(run_project)["pipeline"]:
        config = update_step(run_project, step, "complete", force=True, force_reason=REASON)

    assert config["status"] == "complete"


def test_an_unpaused_completion_does_not_invent_a_status_change(run_project, mocker):
    _gate(mocker)
    config = update_step(run_project, "project", "complete")

    assert config["status"] == "in_progress"


def test_a_lifecycle_set_pause_is_not_lifted(run_project, mocker):
    """`needs_validation` has a SECOND producer: phase_task_lifecycle writes it to
    mean "deploy completed while other phase tasks are still non-terminal", and
    resolve_next_dispatch branches on it. update_step() has no drivability guard
    of its own, so an unconditional reset would silently lift that pause — the
    halt-a-healthy-run failure in reverse."""
    _gate(mocker)
    path = run_project / "shipwright_run_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["status"] = "needs_validation"          # set by the lifecycle, no issues
    path.write_text(json.dumps(config), encoding="utf-8")

    result = update_step(run_project, "project", "complete", force=True, force_reason=REASON)

    assert result["status"] == "needs_validation"
    assert "project" in result["completed_steps"]


# --------------------------------------------------------------------------- #
# R4 — a step with no validator recorded gate_result "pass"
# --------------------------------------------------------------------------- #

def test_a_step_with_no_validator_records_not_checked(run_project):
    """`validate_phase` returns (True, []) when `_VALIDATORS` has no entry for the
    step. `security` is an accepted --step with no validator, so the record
    asserted the gate PASSED where no gate exists — byte-identical to a genuine
    clean-gate override."""
    config = update_step(run_project, "security", "complete", force=True, force_reason=REASON)

    record = config[VALIDATION_OVERRIDES_KEY][-1]
    assert record["gate_result"] == "not_checked"
    assert record["waived"] is False
    assert record["overridden_issues"] == []


def test_a_step_with_a_validator_still_records_pass(run_project, mocker):
    _gate(mocker)
    update_step(run_project, "project", "complete", force=True, force_reason=REASON)

    assert _overrides(run_project)[-1]["gate_result"] == "pass"


def test_run_phase_gate_reports_whether_a_validator_existed(run_project):
    """The distinction is made at the gate, not guessed at the record."""
    _asks, _informs, checked = run_phase_gate(run_project, "security")
    assert checked is False

    _asks, _informs, checked = run_phase_gate(run_project, "project")
    assert checked is True


# --------------------------------------------------------------------------- #
# R8 — a critical-gate crash discarded the findings it was meant to extend
# --------------------------------------------------------------------------- #

def test_a_critical_gate_crash_keeps_the_real_findings(run_project, mocker, monkeypatch):
    """`_read_latest_phase_quality_finding` stat()s inside a sorted() key over a
    glob, so a file vanishing mid-scan raises. That replaced the ask/inform issues
    validate_phase had already produced with a single synthetic gate-error — the
    record then misrepresented what was actually overridden."""
    monkeypatch.setenv("SHIPWRIGHT_ENFORCE_CRITICAL_GATES", "1")
    _gate(mocker, ASK, INFORM)
    mocker.patch(
        "orchestrator_pkg.validation_record._read_latest_phase_quality_finding",
        side_effect=FileNotFoundError("vanished mid-glob"),
    )

    ask_issues, inform_issues, checked = run_phase_gate(run_project, "project")

    assert checked is True
    assert ASK in ask_issues                       # the real finding survived
    assert inform_issues == [INFORM]               # …and so did the inform note
    assert any(GATE_ERROR_PREFIX in i["message"] for i in ask_issues)
    assert "FileNotFoundError" in "".join(i["message"] for i in ask_issues)


def test_a_validate_phase_crash_still_yields_a_single_gate_error(run_project, mocker):
    mocker.patch("phase_validators.validate_phase", side_effect=RuntimeError("boom"))

    ask_issues, inform_issues, checked = run_phase_gate(run_project, "project")

    assert checked is True                          # a validator exists; it blew up
    assert len(ask_issues) == 1
    assert GATE_ERROR_PREFIX in ask_issues[0]["message"]
    assert inform_issues == []


# --------------------------------------------------------------------------- #
# R10 — the gate crash lost its traceback
# --------------------------------------------------------------------------- #

def test_a_gate_crash_writes_its_traceback_to_stderr(run_project, mocker, capsys):
    """The exception is swallowed and never re-raised, so without this the frames
    existed nowhere — the record stayed readable but the bug became undebuggable."""
    mocker.patch("phase_validators.validate_phase", side_effect=RuntimeError("boom"))

    run_phase_gate(run_project, "project")

    err = capsys.readouterr().err
    assert "Traceback" in err
    assert "RuntimeError: boom" in err


# --------------------------------------------------------------------------- #
# R9 — inform notes duplicated on the pause -> force flow
# --------------------------------------------------------------------------- #

def test_inform_notes_do_not_duplicate_across_a_forced_retry(run_project, mocker):
    """The gate now re-runs under force, so the same inform issues were appended
    twice. `validation_notes` has no cap, and update_build_dashboard renders one
    line per entry into a TRACKED artifact."""
    _gate(mocker, ASK, INFORM)
    update_step(run_project, "project", "complete")          # pause, records once
    update_step(run_project, "project", "complete", force=True, force_reason=REASON)

    notes = load_run_config(run_project)["validation_notes"]
    assert notes == [{"step": "project", **INFORM}]


def test_a_distinct_finding_from_the_same_step_survives(run_project, mocker):
    """Dedup is on (step, message), not on step. The split loop re-enters plan and
    build once per split and `_validate_plan` validates only the CURRENT split, so
    plan/01's notes describe different artifacts than plan/02's — wiping every note
    for the step would delete real findings."""
    other = {"severity": "inform", "message": "split 02: fixture missing"}
    _gate(mocker, INFORM)
    update_step(run_project, "plan", "complete", force=True, force_reason=REASON)
    _gate(mocker, INFORM, other)          # split 02: one repeat, one new
    update_step(run_project, "plan", "complete", force=True, force_reason=REASON)

    notes = load_run_config(run_project)["validation_notes"]
    assert notes == [{"step": "plan", **INFORM}, {"step": "plan", **other}]


def test_another_steps_pause_is_neither_lifted_nor_erased(run_project, mocker):
    """The pop used to run unfiltered while only the status reset was narrowed, so
    completing step B destroyed step A's findings and left the run parked in
    needs_validation with nothing on disk to say why."""
    _gate(mocker, ASK)
    update_step(run_project, "test", "complete")            # pauses on `test`
    _gate(mocker)
    update_step(run_project, "design", "complete", force=True, force_reason=REASON)

    config = load_run_config(run_project)
    assert config["status"] == "needs_validation"
    assert config["validation_issues"] == [{"step": "test", **ASK}]


def test_notes_for_other_steps_survive(run_project, mocker):
    """Dedup is per-step — it must not wipe another step's notes."""
    _gate(mocker, INFORM)
    update_step(run_project, "project", "complete", force=True, force_reason=REASON)
    update_step(run_project, "design", "complete", force=True, force_reason=REASON)

    steps = [n["step"] for n in load_run_config(run_project)["validation_notes"]]
    assert sorted(steps) == ["design", "project"]


# --------------------------------------------------------------------------- #
# R11 — CLI and library disagreed on when a reason is required
# --------------------------------------------------------------------------- #

def _cli(project_root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT, "update-step", "--project-root", str(project_root),
         "--step", "project", *extra],
        capture_output=True, text=True,
    )


def test_force_with_a_non_complete_status_is_not_refused(run_project):
    """`update_step` only demands a reason for a completion; the CLI demanded it
    for any status. Nothing is overridden by marking a step in_progress."""
    result = _cli(run_project, "--status", "in_progress", "--force")

    assert result.returncode == 0, result.stderr


def test_a_driven_run_stays_inert_instead_of_erroring(tmp_project):
    """The arg check ran BEFORE the drivability guard, so a driven single_session
    run that used to no-op with exit 0 started exiting 2. An inert command must
    stay inert."""
    (tmp_project / "shipwright_run_config.json").write_text(json.dumps({
        "schemaVersion": 2, "mode": "single_session", "status": "in_progress",
        "current_step": "project", "completed_steps": [], "pipeline": ["project"],
        "phase_tasks": [], "runConditions": {},
    }), encoding="utf-8")

    result = _cli(tmp_project, "--status", "complete", "--force")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state_mutated"] is False


def test_a_reasonless_forced_completion_is_still_refused(run_project):
    """The rule that matters is unchanged."""
    result = _cli(run_project, "--status", "complete", "--force")

    assert result.returncode != 0
    assert "--force-reason" in result.stderr

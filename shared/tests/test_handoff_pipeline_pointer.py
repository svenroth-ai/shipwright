"""What the pipeline block SAYS about the dispatch pointer must be earned.

Reproductions for R2 (a pointer parked on an undispatched successor was called
"Currently dispatched"), R7 (an unhashable status crashed the renderer, and the
Stop hook then skipped the handoff silently) and R6 (the drift guard checked the
direction its own docstring disclaimed) — all found by the Stage-2 code review and
Stage-3 doubt review of `iterate-2026-07-27-phase-gate-override-evidence`.

Each test here FAILS against f6179f6e. Sibling:
`test_handoff_pipeline_tally.py` covers what the block COUNTS.
"""
from __future__ import annotations

import json
from pathlib import Path

from lib.handoff_phase_status import (
    FINISHED_STATUSES,
    INTERRUPTED_STATUSES,
    KNOWN_STATUSES,
    TERMINAL_STATUSES,
)
from lib.handoff_pipeline import LOOP_STATE_REL_PATH, render_pipeline_phases

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ["project", "design", "plan", "build", "test", "changelog", "deploy"]


def _task(phase, status, task_id=None, split=None):
    return {
        "phaseTaskId": task_id or f"ptk-{phase}-{split or '0'}",
        "phase": phase,
        "splitId": split,
        "status": status,
    }


def _write_loop_state(project_root, **fields):
    path = project_root / LOOP_STATE_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields), encoding="utf-8")


def _render(project_root, config):
    return "\n".join(render_pipeline_phases(project_root, config))

# --------------------------------------------------------------------------- #
# R2 — a pointer parked on an undispatched successor was called "dispatched"
# --------------------------------------------------------------------------- #

def test_attempt_zero_is_next_up_not_currently_dispatched(tmp_project):
    """`advance_pointer` points at the SUCCESSOR and resets attempt to 0; only
    `record_dispatch` raises it. So attempt 0 is the most common resume state —
    last phase applied, next not yet started — and it was rendered as a live
    dispatch, next to "Interrupted: none"."""
    config = {
        "pipeline": PIPELINE,
        "phase_tasks": [_task("project", "done"), _task("design", "awaiting_launch")],
    }
    _write_loop_state(
        tmp_project, currentPhaseTaskId="ptk-design-0", attempt=0, status="running",
    )
    out = _render(tmp_project, config)

    assert "Currently dispatched" not in out
    assert "- **Next up**: `design` (status `awaiting_launch`) — pointed at, not yet dispatched" in out


def test_a_real_dispatch_is_still_called_dispatched(tmp_project):
    config = {
        "pipeline": PIPELINE,
        "phase_tasks": [_task("project", "done"), _task("design", "in_progress")],
    }
    _write_loop_state(
        tmp_project, currentPhaseTaskId="ptk-design-0", attempt=2, status="running",
    )
    out = _render(tmp_project, config)

    assert "- **Currently dispatched**: `design` (status `in_progress`, attempt 2)" in out
    assert "Next up" not in out


def test_an_in_progress_task_is_dispatched_whatever_the_counter_says(tmp_project):
    """The task's own status is the stronger signal: `claim_phase_task` sets
    `in_progress` under CAS at dispatch time, while `attempt` is a retry counter
    that recovery resets to 0. So `in_progress` with attempt 0 is a dispatched
    task with a reset counter, not an undispatched one."""
    config = {"pipeline": PIPELINE, "phase_tasks": [_task("build", "in_progress")]}
    _write_loop_state(tmp_project, currentPhaseTaskId="ptk-build-0", attempt=0)
    out = _render(tmp_project, config)

    assert "- **Currently dispatched**: `build` (status `in_progress`)" in out
    assert "Next up" not in out


def test_a_terminal_task_under_the_pointer_is_not_called_dispatched(tmp_project):
    """`recover_single_session` leaves the pointer AND the attempt counter alone
    for a terminal force-status, so after `--force-status skipped` the same phase
    was rendered as banked in the Finished list and in flight on the pointer line
    at the same time — R5's defect shape recreated on the pointer."""
    config = {
        "pipeline": PIPELINE,
        "phase_tasks": [_task("build", "skipped")],
    }
    _write_loop_state(tmp_project, currentPhaseTaskId="ptk-build-0", attempt=2)
    out = _render(tmp_project, config)

    assert "Currently dispatched" not in out
    assert "- **Dispatch pointer**: `build` (status `skipped`) — terminal; " \
           "the loop has not moved on yet" in out
    assert "- **Finished**: 1 of 7 (build)" in out


def test_a_failed_task_under_the_pointer_is_not_called_dispatched(tmp_project):
    config = {"pipeline": PIPELINE, "phase_tasks": [_task("build", "failed")]}
    _write_loop_state(tmp_project, currentPhaseTaskId="ptk-build-0", attempt=3)
    out = _render(tmp_project, config)

    assert "Currently dispatched" not in out
    assert "- **Failed**: `build` — terminal, not finished" in out
    assert "terminal; the loop has not moved on yet" in out


def test_a_recovered_task_is_not_called_dispatched_despite_its_attempt(tmp_project):
    """`recover-phase-task --force-status awaiting_launch` (the DEFAULT, and exempt
    from the drivability guard) releases the claim without touching
    run_loop_state.json, so the attempt counter survives. Treating a counted
    attempt as evidence printed "Currently dispatched … (status `awaiting_launch`,
    attempt 2)" — a line contradicting itself one recovery after the claim was
    released. The counter records that a dispatch HAPPENED, not that one is live."""
    config = {"pipeline": PIPELINE, "phase_tasks": [_task("build", "awaiting_launch")]}
    _write_loop_state(tmp_project, currentPhaseTaskId="ptk-build-0", attempt=2)
    out = _render(tmp_project, config)

    assert "Currently dispatched" not in out
    assert "- **Next up**: `build` (status `awaiting_launch`) — pointed at, not yet dispatched" in out


def test_a_backlog_task_with_attempts_is_not_called_dispatched(tmp_project):
    config = {"pipeline": PIPELINE, "phase_tasks": [_task("build", "backlog")]}
    _write_loop_state(tmp_project, currentPhaseTaskId="ptk-build-0", attempt=5)

    assert "Currently dispatched" not in _render(tmp_project, config)


def test_a_missing_attempt_is_treated_as_not_dispatched(tmp_project):
    """Absent is not evidence of a dispatch — do not assert one."""
    config = {"pipeline": PIPELINE, "phase_tasks": [_task("design", "awaiting_launch")]}
    _write_loop_state(tmp_project, currentPhaseTaskId="ptk-design-0")
    out = _render(tmp_project, config)

    assert "Currently dispatched" not in out
    assert "**Next up**" in out


# --------------------------------------------------------------------------- #
# R7 — an unhashable status crashed the renderer, and the Stop hook ate it
# --------------------------------------------------------------------------- #

def test_an_unhashable_status_does_not_raise(tmp_project):
    """`status in FINISHED_STATUSES` raised TypeError for a list/dict status. The
    Stop hook's outer `except Exception` then skipped the handoff SILENTLY —
    worse than a crash for a document whose job is saying where you are."""
    config = {
        "pipeline": ["project"],
        "phase_tasks": [_task("project", ["in_progress"]), _task("design", {"a": 1})],
    }
    out = _render(tmp_project, config)

    assert "## Pipeline Phases" in out
    assert "- **Finished**: 0 of 2" in out   # 2 tasks planned, 1-step pipeline
    assert out.count("| unknown | unknown |") == 2


def test_a_none_status_renders_as_unknown(tmp_project):
    config = {"pipeline": ["project"], "phase_tasks": [_task("project", None)]}
    out = _render(tmp_project, config)

    # NOT "no": a categorical not-finished verdict about a status the renderer
    # just admitted it could not read is itself a false statement.
    assert "| project | — | unknown | unknown |" in out


# --------------------------------------------------------------------------- #
# R6 — the drift guard checked the direction its docstring disclaimed
# --------------------------------------------------------------------------- #

def test_the_drift_guard_fails_on_an_unclassified_new_status():
    """The predecessor asserted `FINISHED_STATUSES <= declared` — a subset check
    that stays green when a SEVENTH status is added, while the renderer silently
    classifies it as not-finished. Pin the whole vocabulary instead, so a schema
    addition forces an explicit decision here."""
    schema = json.loads(
        (REPO_ROOT / "shared" / "schemas" / "run_config.v2.schema.json")
        .read_text(encoding="utf-8"),
    )
    declared = set(schema["$defs"]["PhaseTaskStatus"]["enum"])

    assert declared == KNOWN_STATUSES, (
        f"run_config.v2.schema.json declares {sorted(declared)} but "
        f"handoff_pipeline classifies {sorted(KNOWN_STATUSES)}. A status the "
        "renderer does not classify is silently counted as not-finished — "
        "classify it in _finished_verdict and add it to KNOWN_STATUSES."
    )
    assert FINISHED_STATUSES < KNOWN_STATUSES
    assert INTERRUPTED_STATUSES < KNOWN_STATUSES
    assert TERMINAL_STATUSES < KNOWN_STATUSES

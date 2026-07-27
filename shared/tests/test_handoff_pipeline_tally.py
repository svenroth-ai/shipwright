"""What the pipeline block COUNTS must not overstate progress.

Reproductions for R1 (the finished tally denominated against tasks-planned-so-far)
and R5 (the finished list dropped the split, and a failed phase appeared in no
bullet) — both found by the Stage-2 code review and Stage-3 doubt review of
`iterate-2026-07-27-phase-gate-override-evidence` (merged f6179f6e).

Every one is the same failure class the predecessor existed to remove: the
document states something that is not so. Each test here FAILS against f6179f6e.
Sibling: `test_handoff_pipeline_pointer.py` covers what the block SAYS about the
dispatch pointer and about a malformed status.
"""
from __future__ import annotations

import json

from lib.handoff_pipeline import LOOP_STATE_REL_PATH, render_pipeline_phases

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
# R1 — the tally denominated against tasks-planned-so-far, not the pipeline
# --------------------------------------------------------------------------- #

def test_the_tally_counts_against_the_pipeline_not_against_planned_tasks(tmp_project):
    """`create_config` seeds ONE phase task; successors are appended as phases
    complete. Denominating against `len(phase_tasks)` made a run 1-of-7 read as
    "1 of 2" — an overstatement that is worst exactly when someone is resuming."""
    config = {
        "pipeline": PIPELINE,
        "status": "in_progress",
        "phase_tasks": [_task("project", "done"), _task("design", "awaiting_launch")],
    }
    out = _render(tmp_project, config)

    assert "- **Finished**: 1 of 7" in out
    assert "1 of 2" not in out


def test_the_block_says_phase_tasks_are_planned_incrementally(tmp_project):
    """The table can only show what has been planned. Saying so is the difference
    between an incomplete view and a misleading one."""
    config = {
        "pipeline": PIPELINE,
        "phase_tasks": [_task("project", "done")],
    }
    out = _render(tmp_project, config)

    assert "planned incrementally" in out
    assert "1 of 7" in out


def test_a_missing_pipeline_key_falls_back_to_the_task_count(tmp_project):
    """Legacy / hand-written configs have no `pipeline`. Degrade, do not crash."""
    config = {"phase_tasks": [_task("project", "done"), _task("design", "done")]}
    out = _render(tmp_project, config)

    assert "- **Finished**: 2 of 2" in out


def test_a_multi_split_run_counts_every_planned_task(tmp_project):
    """`plan` and `build` expand once per frozen split, so the denominator is
    `len(pipeline) + 2*(splits-1)` — here 3 + 2 = 5."""
    config = {
        "pipeline": ["project", "plan", "build"],
        "splits_frozen": ["01", "02"],
        "phase_tasks": [
            _task("project", "done"),
            _task("plan", "done", split="01"),
            _task("build", "done", split="01"),
            _task("plan", "done", split="02"),
            _task("build", "in_progress", split="02"),
        ],
    }
    out = _render(tmp_project, config)

    assert "- **Finished**: 4 of 5" in out


def test_a_split_run_with_every_split_built_is_not_reported_complete(tmp_project):
    """The `max(pipeline, tasks)` heuristic was still short for split runs: a
    3-split run that had finished plan+build for every split rendered "8 of 8" —
    a categorical 100% claim with test, changelog and deploy still unplanned."""
    config = {
        "pipeline": PIPELINE,                       # 7 steps
        "splits_frozen": ["01", "02", "03"],        # +2 per extra split = 11
        "phase_tasks": [
            _task("project", "done"), _task("design", "done"),
            _task("plan", "done", split="01"), _task("build", "done", split="01"),
            _task("plan", "done", split="02"), _task("build", "done", split="02"),
            _task("plan", "done", split="03"), _task("build", "done", split="03"),
        ],
    }
    out = _render(tmp_project, config)

    assert "- **Finished**: 8 of 11" in out
    assert "8 of 8" not in out


def test_a_legacy_off_pipeline_phase_is_counted(tmp_project):
    """`legacy_migration` drops `security` from `pipeline` but leaves its phase
    task in place, and the state machine keeps the legacy security -> changelog
    edge. Counting against `pipeline` alone read "6 of 7" with changelog AND
    deploy still unplanned."""
    config = {
        "pipeline": PIPELINE,                      # 7, security already migrated out
        "phase_tasks": [
            _task("project", "done"), _task("design", "done"),
            _task("plan", "done"), _task("build", "done"),
            _task("test", "done"), _task("security", "skipped"),
        ],
    }
    out = _render(tmp_project, config)

    assert "- **Finished**: 6 of 8" in out
    assert "6 of 7" not in out


def test_a_bad_splits_frozen_value_falls_back_instead_of_crashing(tmp_project):
    config = {
        "pipeline": ["project", "plan"],
        "splits_frozen": "not-a-list",
        "phase_tasks": [_task("project", "done")],
    }
    assert "- **Finished**: 1 of 2" in _render(tmp_project, config)


# --------------------------------------------------------------------------- #
# R5 — splits dropped from the finished list; failures named nowhere
# --------------------------------------------------------------------------- #

def test_the_finished_list_carries_the_split(tmp_project):
    """`build` read as finished AND interrupted at once, because the tally used
    bare phase names while the Interrupted line used phase + split."""
    config = {
        "pipeline": ["project", "plan", "build"],
        "phase_tasks": [
            _task("plan", "done", split="01"),
            _task("build", "done", split="01"),
            _task("build", "in_progress", split="02"),
        ],
    }
    out = _render(tmp_project, config)

    finished_line = [ln for ln in out.splitlines() if ln.startswith("- **Finished**")][0]
    assert "build (split 01)" in finished_line
    assert "plan (split 01)" in finished_line


def test_a_failed_phase_is_named_in_its_own_bullet(tmp_project):
    """A run that died at build rendered "Interrupted: none — no phase is
    mid-flight", i.e. nothing to pick up, for a dead run."""
    config = {
        "pipeline": ["project", "build"],
        "status": "failed",
        "phase_tasks": [_task("project", "done"), _task("build", "failed")],
    }
    out = _render(tmp_project, config)

    assert "- **Failed**: `build` — terminal, not finished" in out
    assert "- **Interrupted**: none — no phase is mid-flight" in out


def test_failed_and_interrupted_are_reported_separately(tmp_project):
    config = {
        "pipeline": ["plan", "build"],
        "phase_tasks": [
            _task("plan", "failed", split="01"),
            _task("build", "in_progress", split="02"),
        ],
    }
    out = _render(tmp_project, config)

    assert "- **Failed**: `plan` (split `01`) — terminal, not finished" in out
    assert "- **Interrupted**: `build` (split `02`) — started, not finished" in out



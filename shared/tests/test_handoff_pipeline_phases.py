"""The session handoff states which phases are finished and which was interrupted.

FR-01.01 (E): *"Given a run that was interrupted part-way, when it is picked up
again, then it continues at the phase it had reached rather than starting over,
and the document a person reads on returning states which phases are finished and
which one was interrupted — the run already knows this; the point is that the
person is told without having to ask."*

The continuation half already worked. The document half did not: the handoff's
own source comment said it "does not track in-flight phase markers", and its
nearest equivalent — `## Recovery` → `N phases completed` — counts distinct
`phase_completed` **events**, saying nothing about what was interrupted.

Nothing here builds resume state. These tests pin that already-held state is
*rendered*, and that a phase which merely started is never counted as finished.
"""
from __future__ import annotations

import json
from pathlib import Path

from lib.handoff_pipeline import (
    FINISHED_STATUSES,
    LOOP_STATE_REL_PATH,
    render_pipeline_phases,
)
from tools.generate_session_handoff import generate_handoff

REPO_ROOT = Path(__file__).resolve().parents[2]


def _task(phase, status, task_id=None, split=None):
    return {
        "phaseTaskId": task_id or f"ptk-{phase}",
        "phase": phase,
        "splitId": split,
        "status": status,
    }


INTERRUPTED_RUN = {
    "status": "in_progress",
    "phase_tasks": [
        _task("project", "done"),
        _task("design", "skipped"),
        _task("plan", "done", split="01-core"),
        _task("build", "in_progress", task_id="ptk-build", split="01-core"),
        _task("test", "awaiting_launch"),
    ],
}


def _write_loop_state(project_root, **fields):
    path = project_root / LOOP_STATE_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields), encoding="utf-8")


def _render(project_root, run_config=INTERRUPTED_RUN):
    return "\n".join(render_pipeline_phases(project_root, run_config))


# --------------------------------------------------------------------------- #
# Finished, interrupted, and the difference between them
# --------------------------------------------------------------------------- #

def test_finished_phases_are_named_and_tallied(tmp_project):
    out = _render(tmp_project)

    assert "## Pipeline Phases" in out
    # done + skipped = 3 of 5. The in_progress build is NOT among them.
    assert "- **Finished**: 3 of 5 (project, design, plan)" in out
    assert "build" not in out.split("- **Finished**")[1].split("\n")[0]


def test_the_interrupted_phase_is_named_as_interrupted(tmp_project):
    out = _render(tmp_project)

    assert "- **Interrupted**: `build` (split `01-core`) — started, not finished" in out


def test_a_phase_that_merely_started_does_not_count_as_finished(tmp_project):
    """The whole point, stated three ways: in the tally, in the table verdict, and
    in words a person reading the document does not have to infer."""
    out = _render(tmp_project)

    assert "| build | 01-core | in_progress | **no — interrupted** |" in out
    assert "A phase that merely STARTED is not finished" in out
    assert "only `done` / `skipped` count" in out


def test_a_run_with_nothing_mid_flight_says_so(tmp_project):
    config = {"status": "complete", "phase_tasks": [_task("project", "done")]}
    out = "\n".join(render_pipeline_phases(tmp_project, config))

    assert "- **Interrupted**: none — no phase is mid-flight" in out


def test_a_failed_phase_is_not_counted_as_finished_either(tmp_project):
    config = {"phase_tasks": [_task("project", "done"), _task("design", "failed")]}
    out = "\n".join(render_pipeline_phases(tmp_project, config))

    assert "- **Finished**: 1 of 2" in out
    assert "| design | — | failed | **no — failed** |" in out


def test_finished_statuses_match_the_run_config_schema():
    """Drift guard: the status vocabulary is owned by phase_task_lifecycle and
    declared in the shared schema. A new terminal status added there must not
    leave this renderer silently miscounting."""
    schema = json.loads(
        (REPO_ROOT / "shared" / "schemas" / "run_config.v2.schema.json")
        .read_text(encoding="utf-8"),
    )
    declared = set(schema["$defs"]["PhaseTaskStatus"]["enum"])

    assert FINISHED_STATUSES <= declared, (
        f"handoff_pipeline.FINISHED_STATUSES has {FINISHED_STATUSES - declared} "
        "which the schema does not declare"
    )


# --------------------------------------------------------------------------- #
# The dispatch pointer the loop already holds
# --------------------------------------------------------------------------- #

def test_the_dispatch_pointer_is_rendered(tmp_project):
    _write_loop_state(
        tmp_project, runId="run-1", currentPhaseTaskId="ptk-build",
        attempt=2, status="running",
    )
    out = _render(tmp_project)

    assert "- **Currently dispatched**: `build` (split `01-core`) " \
           "(status `in_progress`, attempt 2)" in out
    assert "- **Loop status**: running" in out


def test_a_pointer_naming_no_known_task_is_labelled_stale(tmp_project):
    """Loop state and run config are separate files. A pointer that resolves to
    nothing means one of them is behind — say so rather than assert a phase."""
    _write_loop_state(tmp_project, currentPhaseTaskId="ptk-vanished", attempt=1)
    out = _render(tmp_project)

    assert "`ptk-vanished` — stale pointer, no such entry in `phase_tasks[]`" in out
    assert "Currently dispatched**: `vanished`" not in out


def test_a_non_numeric_attempt_is_omitted_rather_than_printed(tmp_project):
    _write_loop_state(tmp_project, currentPhaseTaskId="ptk-build", attempt="lots")
    out = _render(tmp_project)

    assert "attempt" not in out
    assert "- **Currently dispatched**: `build` (split `01-core`) (status `in_progress`)" in out


def test_no_loop_state_still_renders_the_phase_table(tmp_project):
    out = _render(tmp_project)

    assert "Currently dispatched" not in out
    assert "- **Finished**: 3 of 5" in out
    assert "| build | 01-core | in_progress | **no — interrupted** |" in out


def test_corrupt_loop_state_degrades_without_crashing(tmp_project):
    """The loop rewrites this file while the handoff may be reading it, so a
    partial read is expected rather than exceptional."""
    path = tmp_project / LOOP_STATE_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"runId": "run-1", "currentPhas', encoding="utf-8")

    out = _render(tmp_project)

    assert "Currently dispatched" not in out
    assert "- **Finished**: 3 of 5" in out


def test_a_loop_state_that_is_not_an_object_is_ignored(tmp_project):
    path = tmp_project / LOOP_STATE_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")

    assert "Currently dispatched" not in _render(tmp_project)


def test_multiple_in_progress_tasks_are_all_named(tmp_project):
    config = {"phase_tasks": [
        _task("build", "in_progress", task_id="ptk-b1", split="01"),
        _task("build", "in_progress", task_id="ptk-b2", split="02"),
    ]}
    out = "\n".join(render_pipeline_phases(tmp_project, config))

    assert out.count("— started, not finished") == 2
    assert "- **Finished**: 0 of 2" in out


# --------------------------------------------------------------------------- #
# Malformed producer data must not corrupt the document
# --------------------------------------------------------------------------- #

def test_markdown_delimiters_in_producer_data_cannot_break_the_table(tmp_project):
    config = {"phase_tasks": [_task("bui|ld", "done", split="a\nb")]}
    out = "\n".join(render_pipeline_phases(tmp_project, config))

    row = [ln for ln in out.splitlines() if ln.startswith("| bui")][0]
    assert row == "| bui\\|ld | a b | done | yes |"
    assert row.count("|") - row.count("\\|") == 5      # 5 real delimiters, no more


def test_non_mapping_rows_are_skipped(tmp_project):
    config = {"phase_tasks": ["nonsense", None, _task("project", "done")]}
    out = "\n".join(render_pipeline_phases(tmp_project, config))

    assert "- **Finished**: 1 of 1" in out


# --------------------------------------------------------------------------- #
# Nothing to say → say nothing (no placeholder rows)
# --------------------------------------------------------------------------- #

def test_a_config_without_phase_tasks_renders_nothing(tmp_project):
    assert render_pipeline_phases(tmp_project, {"status": "complete"}) == []
    assert render_pipeline_phases(tmp_project, {"phase_tasks": []}) == []
    assert render_pipeline_phases(tmp_project, {"phase_tasks": "nope"}) == []
    assert render_pipeline_phases(tmp_project, None) == []


def test_a_legacy_project_handoff_gains_no_pipeline_block(tmp_project):
    """End-to-end: adopted / standalone projects have no phase_tasks, and their
    handoff must be unchanged by this feature."""
    assert "## Pipeline Phases" not in generate_handoff(tmp_project)


# --------------------------------------------------------------------------- #
# End-to-end through the real handoff document
# --------------------------------------------------------------------------- #

def test_generate_handoff_renders_the_block_above_the_legacy_checkpoint(tmp_project):
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(INTERRUPTED_RUN), encoding="utf-8",
    )
    _write_loop_state(
        tmp_project, currentPhaseTaskId="ptk-build", attempt=1, status="running",
    )

    content = generate_handoff(tmp_project, session_id="sess-1")

    assert "## Pipeline Phases" in content
    assert "- **Interrupted**: `build` (split `01-core`) — started, not finished" in content
    # The authoritative view comes before the event-derived and legacy ones.
    assert content.index("## Pipeline Phases") < content.index("## Legacy build state")

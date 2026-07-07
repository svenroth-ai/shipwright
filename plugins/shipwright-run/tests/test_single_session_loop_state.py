"""Tests for the single-session orchestrator LOOP-STATE persistence (SS1 scaffold).

Campaign 2026-07-07-single-session-pipeline / SS1.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from single_session.loop_state import (  # noqa: E402
    LOOP_STATE_REL_PATH,
    LOOP_STATE_SCHEMA_VERSION,
    LOOP_STATUSES,
    advance_pointer,
    init_loop_state,
    load_loop_state,
    loop_state_path,
    record_dispatch,
    save_loop_state,
    set_status,
)


# ---- shape ----


def test_init_loop_state_shape():
    st = init_loop_state("run-a1b2c3d4", current_phase_task_id="ptk-11112222")
    assert st["schemaVersion"] == LOOP_STATE_SCHEMA_VERSION
    assert st["runId"] == "run-a1b2c3d4"
    assert st["currentPhaseTaskId"] == "ptk-11112222"
    assert st["attempt"] == 0
    assert st["lastCompletedPhaseTaskId"] is None
    assert st["status"] == "running"
    assert st["createdAt"] and st["updatedAt"]


def test_init_loop_state_allows_no_seed_task():
    st = init_loop_state("run-a1b2c3d4")
    assert st["currentPhaseTaskId"] is None


# ---- path is distinct from the campaign loop ----


def test_loop_state_path_is_run_scoped_and_distinct_from_campaign(tmp_project):
    p = loop_state_path(tmp_project)
    assert p == tmp_project / ".shipwright" / "run_loop_state.json"
    assert Path(LOOP_STATE_REL_PATH).name == "run_loop_state.json"
    # Must NOT collide with the campaign autonomous loop's loop_state.json.
    assert p.name != "loop_state.json"


# ---- persistence round-trip ----


def test_save_then_load_round_trips(tmp_project):
    st = init_loop_state("run-a1b2c3d4", current_phase_task_id="ptk-aaaa1111")
    save_loop_state(tmp_project, st)
    loaded = load_loop_state(tmp_project)
    # Everything but updatedAt (restamped on save) round-trips exactly.
    assert {k: v for k, v in loaded.items() if k != "updatedAt"} == \
           {k: v for k, v in st.items() if k != "updatedAt"}


def test_save_creates_shipwright_dir(tmp_project):
    assert not (tmp_project / ".shipwright").exists()
    save_loop_state(tmp_project, init_loop_state("run-a1b2c3d4"))
    assert (tmp_project / ".shipwright" / "run_loop_state.json").exists()


def test_save_writes_valid_json(tmp_project):
    save_loop_state(tmp_project, init_loop_state("run-a1b2c3d4"))
    raw = (tmp_project / ".shipwright" / "run_loop_state.json").read_text(encoding="utf-8")
    assert json.loads(raw)["runId"] == "run-a1b2c3d4"


def test_load_absent_returns_none(tmp_project):
    assert load_loop_state(tmp_project) is None


def test_save_restamps_updated_at(tmp_project):
    st = init_loop_state("run-a1b2c3d4")
    st["updatedAt"] = "2020-01-01T00:00:00+00:00"
    save_loop_state(tmp_project, st)
    loaded = load_loop_state(tmp_project)
    assert loaded["updatedAt"] != "2020-01-01T00:00:00+00:00"


# ---- pure mutators ----


def test_record_dispatch_increments_attempt_purely():
    st = init_loop_state("run-a1b2c3d4")
    nxt = record_dispatch(st)
    assert nxt["attempt"] == 1
    assert st["attempt"] == 0, "record_dispatch must not mutate its input"
    assert record_dispatch(nxt)["attempt"] == 2


def test_advance_pointer_moves_to_next_and_resets_attempt():
    st = record_dispatch(init_loop_state("run-a1b2c3d4", current_phase_task_id="ptk-1"))
    nxt = advance_pointer(st, completed_phase_task_id="ptk-1", next_phase_task_id="ptk-2")
    assert nxt["lastCompletedPhaseTaskId"] == "ptk-1"
    assert nxt["currentPhaseTaskId"] == "ptk-2"
    assert nxt["attempt"] == 0
    # purity
    assert st["currentPhaseTaskId"] == "ptk-1"


def test_advance_pointer_terminal_sets_current_none():
    st = init_loop_state("run-a1b2c3d4", current_phase_task_id="ptk-9")
    nxt = advance_pointer(st, completed_phase_task_id="ptk-9", next_phase_task_id=None)
    assert nxt["currentPhaseTaskId"] is None
    assert nxt["lastCompletedPhaseTaskId"] == "ptk-9"


def test_set_status_validated_and_pure():
    st = init_loop_state("run-a1b2c3d4")
    for status in LOOP_STATUSES:
        assert set_status(st, status)["status"] == status
    assert st["status"] == "running", "set_status must not mutate its input"


def test_set_status_rejects_unknown():
    with pytest.raises(ValueError):
        set_status(init_loop_state("run-a1b2c3d4"), "bogus")

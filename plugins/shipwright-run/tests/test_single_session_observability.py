"""Tests for the single-session orchestrator OBSERVABILITY event log (SS5).

Campaign 2026-07-07-single-session-pipeline / SS5.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from single_session import observability as obs  # noqa: E402


# ---- event types + build ----


def test_loop_event_types_are_the_closed_reconciled_set():
    assert obs.LOOP_EVENT_TYPES == (
        "dispatch",
        "phase_result",
        "strict_stop",
        "human_gate_pause",
        "human_gate_resume",
        "resume",
        "recovery",
    )


def test_build_event_shape_and_schema_version():
    ev = obs.build_event("dispatch", "run-a1b2c3d4", phaseTaskId="ptk-1", phase="project")
    assert ev["schemaVersion"] == obs.EVENTS_SCHEMA_VERSION == 1
    assert ev["event"] == "dispatch"
    assert ev["runId"] == "run-a1b2c3d4"
    assert ev["phaseTaskId"] == "ptk-1"
    assert ev["phase"] == "project"
    assert ev["at"]  # stamped


def test_build_event_rejects_unknown_type():
    with pytest.raises(ValueError):
        obs.build_event("bogus", "run-a1b2c3d4")


# ---- path distinctness ----


def test_events_path_is_distinct_from_loop_state_and_pipeline_events(tmp_project):
    p = obs.events_path(tmp_project)
    assert p == tmp_project / ".shipwright" / "run_loop_events.jsonl"
    # Must not collide with the resumable loop pointer or the tracked pipeline log.
    assert p.name != "run_loop_state.json"
    assert p.name != "shipwright_events.jsonl"
    assert p.name != "loop_state.json"


# ---- emit + load round-trip ----


def test_emit_appends_one_jsonl_line_per_event(tmp_project):
    obs.emit(tmp_project, event_type="dispatch", run_id="run-x", phaseTaskId="ptk-1")
    obs.emit(tmp_project, event_type="phase_result", run_id="run-x", ok=True)
    raw = obs.events_path(tmp_project).read_text(encoding="utf-8")
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "dispatch"
    assert json.loads(lines[1])["event"] == "phase_result"


def test_load_events_round_trips(tmp_project):
    obs.emit(tmp_project, event_type="dispatch", run_id="run-x", phaseTaskId="ptk-1")
    obs.emit(tmp_project, event_type="resume", run_id="run-x", resumeAction="dispatch")
    events = obs.load_events(tmp_project)
    assert [e["event"] for e in events] == ["dispatch", "resume"]
    assert events[1]["resumeAction"] == "dispatch"


def test_load_events_absent_returns_empty(tmp_project):
    assert obs.load_events(tmp_project) == []


def test_load_events_tolerates_a_torn_trailing_line(tmp_project):
    obs.emit(tmp_project, event_type="dispatch", run_id="run-x", phaseTaskId="ptk-1")
    # Simulate a crash mid-write leaving a truncated final line.
    with obs.events_path(tmp_project).open("a", encoding="utf-8") as fh:
        fh.write('{"event": "phase_resu')  # no newline, invalid JSON
    events = obs.load_events(tmp_project)
    assert len(events) == 1
    assert events[0]["event"] == "dispatch"


def test_emit_creates_shipwright_dir(tmp_project):
    assert not (tmp_project / ".shipwright").exists()
    obs.emit(tmp_project, event_type="dispatch", run_id="run-x")
    assert obs.events_path(tmp_project).exists()


# ---- best-effort: an IO failure never propagates, but is visible ----


def test_emit_event_swallows_io_error_but_warns(tmp_project, monkeypatch, capsys):
    def _boom(*_a, **_k):
        raise OSError("disk full")

    # Force the append to fail deep in the write path.
    monkeypatch.setattr(Path, "open", _boom)
    # Must NOT raise — telemetry is best-effort.
    obs.emit_event(tmp_project, obs.build_event("recovery", "run-x", phaseTaskId="ptk-9"))
    err = capsys.readouterr().err
    assert "observability emit failed" in err
    assert "recovery" in err


def test_emit_convenience_still_raises_on_bad_type(tmp_project):
    # A bad event_type is a programming error and must surface even through emit().
    with pytest.raises(ValueError):
        obs.emit(tmp_project, event_type="not-a-real-event", run_id="run-x")


def test_emit_event_swallows_non_serializable_field(tmp_project, capsys):
    # A field that slipped past the whitelist (e.g. a Path) makes json.dumps raise
    # TypeError — best-effort emit must NOT propagate it (review finding #4).
    bad = {"schemaVersion": 1, "event": "dispatch", "runId": "run-x", "bad": Path("/x")}
    obs.emit_event(tmp_project, bad)  # must not raise
    assert "observability emit failed" in capsys.readouterr().err
    assert obs.load_events(tmp_project) == []  # nothing written


# ---- typed emitters (loop call sites) ----


def test_emit_dispatch_records_identifiers(tmp_project):
    obs.emit_dispatch(
        tmp_project, run_id="run-x",
        dispatch={"phaseTaskId": "ptk-1", "phase": "build", "splitId": "01"},
        attempt=2, idempotent=True,
    )
    (ev,) = obs.load_events(tmp_project)
    assert ev["event"] == "dispatch"
    assert ev["phaseTaskId"] == "ptk-1"
    assert ev["phase"] == "build"
    assert ev["splitId"] == "01"
    assert ev["attempt"] == 2
    assert ev["idempotent"] is True


def test_emit_phase_result_ok_emits_only_phase_result(tmp_project):
    obs.emit_phase_result(
        tmp_project, run_id="run-x", phase_task_id="ptk-1", phase="build",
        run_status="in_progress", failed=False,
    )
    events = obs.load_events(tmp_project)
    assert [e["event"] for e in events] == ["phase_result"]
    assert events[0]["ok"] is True
    assert events[0]["runStatus"] == "in_progress"


def test_emit_phase_result_failed_also_emits_strict_stop(tmp_project):
    obs.emit_phase_result(
        tmp_project, run_id="run-x", phase_task_id="ptk-1", phase="build",
        run_status="failed", failed=True, reason="boom",
    )
    events = obs.load_events(tmp_project)
    assert [e["event"] for e in events] == ["phase_result", "strict_stop"]
    assert events[0]["ok"] is False
    assert events[1]["reason"] == "boom"

"""F5b folding of context_cost into work_completed (context-cost-meter).

Parity structure with test_iterate_timings_finalize.py — same ``project``
fixture shape, same finalize entry point, proving the context-cost sidecar
coexists with the phase_timings/iterate_timings folds without interfering.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

RUN = "iterate-2026-08-07-context-cost-meter"
SESSION = "sess-finalize"
_VALID_EXTRAS = {"change_type": "tooling", "none_reason": "context-cost-meter unit test"}


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}), encoding="utf-8"
    )
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    return tmp_path


def _write_summary(project: Path, session: str, summary: dict) -> None:
    path = project / ".shipwright" / "compliance" / "context-cost" / f"{session}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary), encoding="utf-8")


def _latest_work_completed(project: Path) -> dict:
    from tools.record_event import read_events
    events = [e for e in read_events(project) if e.get("type") == "work_completed"]
    return events[-1]


def test_finalize_folds_context_cost_alongside_the_other_sidecars(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", SESSION)
    from tools.finalize_iterate import run
    from lib import iterate_phase_groups as ipg

    ipg.append_mark(project, RUN, "scope")
    _write_summary(project, SESSION, {
        "calls": 42, "context_tokens": 4200, "cost_usd": 1.23, "unpriced_calls": 0,
        "cost_complete": True, "by_phase": {"scope": {"calls": 42}},
    })

    run(project, run_id=RUN, event_extras=dict(_VALID_EXTRAS))
    ev = _latest_work_completed(project)

    assert "phase_timings" in ev  # the other sidecar systems, unaffected
    assert "context_cost" in ev
    assert ev["context_cost"]["calls"] == 42
    assert ev["context_cost"]["cost_usd"] == 1.23
    assert ev["context_cost"]["measured_through"] == "F5b"
    assert ev["context_cost"]["measured_at"]  # a timestamp, never blank


def test_finalize_without_a_summary_file_omits_context_cost(project, monkeypatch):
    # No Stop has fired yet in this test session -- graceful absence, not a crash.
    monkeypatch.chdir(project)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "sess-never-stopped")
    from tools.finalize_iterate import run

    run(project, run_id=RUN, event_extras=dict(_VALID_EXTRAS))
    ev = _latest_work_completed(project)

    assert "context_cost" not in ev


def test_finalize_without_session_id_env_var_omits_context_cost(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    from tools.finalize_iterate import run

    run(project, run_id=RUN, event_extras=dict(_VALID_EXTRAS))
    ev = _latest_work_completed(project)

    assert "context_cost" not in ev


def test_finalize_survives_a_malformed_summary_file(project, monkeypatch):
    # A summary file that is valid JSON but not an object (or is corrupt)
    # must never take the whole work_completed event down with it.
    monkeypatch.chdir(project)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", SESSION)
    path = project / ".shipwright" / "compliance" / "context-cost" / f"{SESSION}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    from tools.finalize_iterate import run

    run(project, run_id=RUN, event_extras=dict(_VALID_EXTRAS))
    ev = _latest_work_completed(project)

    assert ev is not None
    assert "context_cost" not in ev

"""F5b folding of iterate_timings into work_completed (measurement only).

Parity structure with test_iterate_phase_timing.py's AC4 — same ``project``
fixture shape, same finalize entry point — proving the two sidecar systems
coexist without interfering with each other.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import iterate_timings as it  # noqa: E402
from lib import iterate_timings_normalize as itn  # noqa: E402

RUN = "iterate-2026-08-04-iterate-timing-attribution"
_VALID_EXTRAS = {"change_type": "tooling", "none_reason": "iterate-timing unit test"}


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}), encoding="utf-8"
    )
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    return tmp_path


def _latest_work_completed(project: Path) -> dict:
    from tools.record_event import read_events
    events = [e for e in read_events(project) if e.get("type") == "work_completed"]
    return events[-1]


def test_finalize_folds_iterate_timings_alongside_phase_timings(project, monkeypatch):
    monkeypatch.chdir(project)
    from tools.finalize_iterate import run
    from lib import iterate_phase_groups as ipg

    ipg.append_mark(project, RUN, "scope")
    it.record_start(project, RUN, name="verification", parent=None,
                    ts="2026-08-04T10:00:00+00:00")
    it.record_producer_span(project, RUN, name="canonical_f0_active", parent="verification",
                            start_utc="2026-08-04T10:00:00+00:00",
                            end_utc="2026-08-04T10:05:00+00:00", duration_ms=300000)
    it.record_end(project, RUN, name="verification", parent=None, ts="2026-08-04T10:05:00+00:00")

    run(project, run_id=RUN, event_extras=dict(_VALID_EXTRAS))
    ev = _latest_work_completed(project)
    assert "phase_timings" in ev  # the OTHER sidecar system, unaffected
    assert "iterate_timings" in ev
    names = {s["name"] for s in ev["iterate_timings"]}
    assert names == {"verification", "canonical_f0_active"}


def test_finalize_without_sidecar_omits_iterate_timings(project, monkeypatch):
    monkeypatch.chdir(project)
    from tools.finalize_iterate import run

    run(project, run_id="iterate-2026-08-04-no-timing", event_extras=dict(_VALID_EXTRAS))
    ev = _latest_work_completed(project)
    assert "iterate_timings" not in ev


def test_finalize_never_overwrites_a_preexisting_field(project, monkeypatch):
    """Existing work_completed events without iterate_timings remain valid;
    an event that already carries the field (e.g. a replay) is untouched."""
    ev = {"iterate_timings": [{"sentinel": True}]}
    itn.fold_into_event(ev, project, RUN)
    assert ev["iterate_timings"] == [{"sentinel": True}]


def test_incomplete_span_persists_as_incomplete_not_zero(project, monkeypatch):
    """A cancelled/interrupted run's unmatched start must show up as
    incomplete/None duration — never a fabricated zero."""
    monkeypatch.chdir(project)
    from tools.finalize_iterate import run

    it.record_start(project, RUN, name="review", parent=None)
    # No matching end — simulates an interrupted session.

    run(project, run_id=RUN, event_extras=dict(_VALID_EXTRAS))
    ev = _latest_work_completed(project)
    review = next(s for s in ev["iterate_timings"] if s["name"] == "review")
    assert review["outcome"] == "incomplete"
    assert review["duration_ms"] is None


def test_malformed_span_is_rejected_the_rest_still_persists(project, monkeypatch):
    """Malformed timing data is rejected at the event-write boundary rather
    than persisted — but a bad entry never voids an otherwise-good run."""
    monkeypatch.chdir(project)
    from tools.finalize_iterate import run

    it.record_start(project, RUN, name="planning", parent=None,
                    ts="2026-08-04T10:00:00+00:00")
    it.record_end(project, RUN, name="planning", parent=None,
                  ts="2026-08-04T10:01:00+00:00")
    # A raw, hand-corrupted line the CLI would never produce on its own.
    sidecar = it.sidecar_path(project, RUN)
    with sidecar.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "span", "name": "not-a-real-span", "parent": None,
                             "start_utc": "x", "end_utc": None, "duration_ms": -9,
                             "attempt": 1, "source": "producer", "outcome": "completed",
                             "extra": {}}) + "\n")

    run(project, run_id=RUN, event_extras=dict(_VALID_EXTRAS))
    ev = _latest_work_completed(project)
    names = {s["name"] for s in ev["iterate_timings"]}
    assert names == {"planning"}
    assert "not-a-real-span" not in names


def test_gate_ordering_and_verdict_unchanged_by_timing_fold(project, monkeypatch):
    """Preserve current verdicts/gates: a missing change_type still rejects,
    identically whether or not a timings sidecar exists."""
    monkeypatch.chdir(project)
    from tools.finalize_iterate import FinalizeGateError, run

    it.record_start(project, RUN, name="planning", parent=None)
    it.record_end(project, RUN, name="planning", parent=None)
    with pytest.raises(FinalizeGateError):
        run(project, run_id=RUN, event_extras={"spec_impact": "none"})  # no change_type

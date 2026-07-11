"""END-TO-END per-split phase-duration integration test
(iterate-2026-07-11-phase-completed-per-split).

B1/M-Pre-1 made a multi-split pipeline phase (build/plan fan out one phase_task
per split) record N ``phase_started`` (un-deduped) but only ONE ``phase_completed``
(record_event deduped by ``phase`` alone, first-wins). So the tracked-log
start+end pair reflected only the FIRST split and the per-phase duration
UNDERCOUNTED. This proves the three components COMPOSE for a real 3-split build:

  1. the multi-session start wrapper  ``lib.phase_event_emit.emit_phase_event``
  2. the stop-hook end wrapper        ``phase_session_stop._record_event``
  3. the event writer + dedup         ``tools/record_event.py`` (real subprocess)

...produce a tracked ``shipwright_events.jsonl`` in which EVERY split's end
survives (so the LAST split's end — which bounds the true phase span — is
present, not just the first), a crash-resume re-emit of the same split is still
deduped, and the compliance phase-count reduction (``{e["phase"] …}``) still
counts the phase exactly once.

Drives the REAL emit wrappers (subprocess → real record_event CLI), like the
sibling ``test_phase_started_emit.py`` — NOT marked ``slow`` so it gates in CI.
category: integration (cross_component coverage — the emit path touches the
``phase_session_stop`` hook).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts" / "hooks"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))

from lib.phase_event_emit import emit_phase_event  # noqa: E402
import phase_session_stop  # noqa: E402

_SPLITS = ("01-foundation", "02-ui", "03-api")


def _ends_of(project_root: Path, phase: str) -> list[dict]:
    path = project_root / "shipwright_events.jsonl"
    events = [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]
    return [e for e in events if e.get("type") == "phase_completed" and e.get("phase") == phase]


def _starts_of(project_root: Path, phase: str) -> list[dict]:
    path = project_root / "shipwright_events.jsonl"
    events = [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]
    return [e for e in events if e.get("type") == "phase_started" and e.get("phase") == phase]


def test_multi_split_build_records_every_split_end(tmp_path):
    """A 3-split build records one start + one end PER split (per-split facts)."""
    proj = tmp_path / "proj"
    proj.mkdir()

    # 1. Three build splits START (multi-session start wrapper → real record_event).
    for split in _SPLITS:
        emit_phase_event(proj, "phase_started", "build",
                         {"phaseTaskId": f"ptk-{split}", "splitId": split, "runId": "r"})

    # 2. Three build splits COMPLETE (stop-hook end wrapper → real record_event).
    for split in _SPLITS:
        phase_session_stop._record_event(proj, "phase_completed", "build",
                                         {"phaseTaskId": f"ptk-{split}", "splitId": split,
                                          "runId": "r"})

    starts = _starts_of(proj, "build")
    ends = _ends_of(proj, "build")

    # Every split is represented on BOTH ends — including the LAST split, whose
    # end bounds the true phase span. Pre-fix, only "01-foundation" survived.
    assert {e["splitId"] for e in starts} == set(_SPLITS)
    assert {e["splitId"] for e in ends} == set(_SPLITS)
    assert len(ends) == 3

    # 3. Crash-resume re-emit of an already-recorded split is still deduped.
    phase_session_stop._record_event(proj, "phase_completed", "build",
                                     {"phaseTaskId": "ptk-01-foundation",
                                      "splitId": "01-foundation", "runId": "r"})
    assert len(_ends_of(proj, "build")) == 3  # no double-count

    # 4. The compliance phase-count reduction still counts the phase ONCE
    #    (distinct phase names), so a multi-split build cannot overcount.
    completed_phases = sorted({e["phase"] for e in _ends_of(proj, "build")})
    assert completed_phases == ["build"]


def test_single_split_phase_unchanged(tmp_path):
    """A single-pass phase (splitId=None) still dedups to exactly one end —
    the historical phase-only behavior is preserved (zero back-compat drift)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    for _ in range(2):  # a re-emit (e.g. crash-resume) of the same phase
        phase_session_stop._record_event(proj, "phase_completed", "project",
                                         {"phaseTaskId": "ptk-p", "splitId": None,
                                          "runId": "r"})
    assert len(_ends_of(proj, "project")) == 1

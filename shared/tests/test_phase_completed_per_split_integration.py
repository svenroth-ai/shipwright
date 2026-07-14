"""END-TO-END per-split phase-duration integration test
(iterate-2026-07-11-phase-completed-per-split).

B1/M-Pre-1 made a multi-split pipeline phase (build/plan fan out one phase_task per
split) record N ``phase_started`` (un-deduped) but only ONE ``phase_completed``
(``record_event`` deduped by ``phase`` alone, first-wins). So the tracked-log
start+end pair reflected only the FIRST split and the per-phase duration
UNDERCOUNTED. The fix made the dedup identity the ``(phase, splitId)`` PAIR.

**Re-homed by ``iterate-2026-07-14-remove-multi-session``.** This test used to drive
the two emitters that existed then — ``lib.phase_event_emit.emit_phase_event`` (the
multi-session start wrapper) and ``phase_session_stop._record_event`` (the stop-hook
end wrapper). Both were deleted with the multi-session engine. The *rule* they
exercised, however, lives in ``shared/scripts/tools/record_event.py``, which is
untouched — so the regression is pinned here at its OWNER, driven through the real
CLI as a real subprocess (exactly how every emitter reaches it).

The surviving emitters — ``orchestrator_pkg.events.record_phase_started`` /
``record_phase_end``, now the SOLE producers of these events — are covered by
``plugins/shipwright-run/tests/test_single_session_phase_started.py`` (unit) and
``integration-tests/test_single_session_sole_mode.py`` (end-to-end, which asserts a
complete start+end pair per split survives a real pipeline run).

category: integration
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECORD_EVENT = _REPO_ROOT / "shared" / "scripts" / "tools" / "record_event.py"

_SPLITS = ("01-foundation", "02-ui", "03-api")


def _record(project_root: Path, event_type: str, phase: str,
            split_id: str | None, ptk: str) -> None:
    """Append an event through the REAL record_event CLI (a real subprocess).

    This is the exact call shape every in-tree emitter uses: ``--detail`` carries the
    payload, and ``--split-id`` is promoted to the top level so the writer can dedup
    on the ``(phase, splitId)`` pair.
    """
    args = [
        sys.executable, str(_RECORD_EVENT),
        "--project-root", str(project_root),
        "--type", event_type,
        "--phase", phase,
        "--detail", json.dumps({"phaseTaskId": ptk, "splitId": split_id, "runId": "r"}),
    ]
    if split_id is not None:
        args += ["--split-id", split_id]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"record_event failed: {proc.stderr}"


def _events_of(project_root: Path, event_type: str, phase: str) -> list[dict]:
    path = project_root / "shipwright_events.jsonl"
    events = [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]
    return [e for e in events if e.get("type") == event_type and e.get("phase") == phase]


def test_multi_split_build_records_every_split_end(tmp_path):
    """A 3-split build records one start + one end PER split (per-split facts)."""
    proj = tmp_path / "proj"
    proj.mkdir()

    for split in _SPLITS:
        _record(proj, "phase_started", "build", split, f"ptk-{split}")
    for split in _SPLITS:
        _record(proj, "phase_completed", "build", split, f"ptk-{split}")

    starts = _events_of(proj, "phase_started", "build")
    ends = _events_of(proj, "phase_completed", "build")

    # Every split is represented on BOTH ends — including the LAST split, whose end
    # bounds the true phase span. Pre-fix, only "01-foundation" survived.
    assert {e["splitId"] for e in starts} == set(_SPLITS)
    assert {e["splitId"] for e in ends} == set(_SPLITS)
    assert len(ends) == 3

    # A crash-resume re-emit of an already-recorded split is still deduped.
    _record(proj, "phase_completed", "build", "01-foundation", "ptk-01-foundation")
    assert len(_events_of(proj, "phase_completed", "build")) == 3  # no double-count

    # The compliance phase-count reduction still counts the phase ONCE (distinct
    # phase names), so a multi-split build cannot overcount.
    assert sorted({e["phase"] for e in _events_of(proj, "phase_completed", "build")}) == ["build"]


def test_single_split_phase_unchanged(tmp_path):
    """A single-pass phase (splitId=None) still dedups to exactly one end — the
    historical phase-only behavior is preserved (zero back-compat drift)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    for _ in range(2):  # a re-emit (e.g. crash-resume) of the same phase
        _record(proj, "phase_completed", "project", None, "ptk-p")
    assert len(_events_of(proj, "phase_completed", "project")) == 1

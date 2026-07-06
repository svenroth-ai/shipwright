"""Capture-seam regression tests (G5).

The empirical record/replay harness needs the *pre-engine* ``GradeInputs`` +
report-extras, so ``grade_context`` was refactored to delegate to
``grade_context_captured`` (additive). These tests pin the two guarantees that
protect G1-G4:

1. ``grade_context`` returns a ReportModel **byte-identical** to
   ``grade_context_captured(...).report`` — the public contract is unchanged.
2. The captured ``GradeInputs`` round-trips through JSON and back into the engine
   to the SAME grade — the offline-replay boundary is sound (this is the
   ``touches_io_boundary`` round-trip probe, at the library level).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from engine_bridge import load_engine
from grade_inputs_projector import (
    GradeComputation,
    grade_context,
    grade_context_captured,
)
from repo_context import RepoContext
from resolve_target import resolve_target


def _context(repo: Path) -> RepoContext:
    return RepoContext(resolve_target(str(repo)))


def test_grade_context_delegates_to_capture_identically(well_run_repo: Path):
    ctx = _context(well_run_repo)
    plain = grade_context(ctx)
    captured = grade_context_captured(ctx)
    assert isinstance(captured, GradeComputation)
    # The public return is byte-identical to the captured report.
    assert dataclasses.asdict(plain) == dataclasses.asdict(captured.report)


def test_capture_exposes_heuristic_inputs_and_extras(well_run_repo: Path):
    captured = grade_context_captured(_context(well_run_repo))
    assert captured.grade_inputs is not None
    assert captured.report_extras is not None
    assert captured.report_extras["routing"]["effective_mode"] == "heuristic"
    # Extras carry exactly the build_report_model side-inputs the replay needs.
    for key in ("target_display", "head_sha", "detail_overrides",
                "provenance_overrides", "network_enabled", "network_enrichments"):
        assert key in captured.report_extras


def test_grade_inputs_round_trip_through_json_reproduces_grade(well_run_repo: Path):
    engine = load_engine()
    captured = grade_context_captured(_context(well_run_repo))
    gi = json.loads(json.dumps(dataclasses.asdict(captured.grade_inputs)))
    gi["expected_dimensions"] = tuple(gi.get("expected_dimensions") or ())
    rehydrated = engine.GradeInputs(**gi)
    report = engine.compute_grade(rehydrated)
    assert report.grade == captured.report.grade
    assert report.score == captured.report.score

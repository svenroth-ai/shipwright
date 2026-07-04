"""Tests for the grade-neutral diff-coverage INFO line (roadmap Phase 1).

Two guarantees:
  1. ``_diff_coverage_block`` loads the gitignored transient report and renders
     an informational line (ok / n/a / absent).
  2. **Grade-neutrality** — the Control-Grade rendering (letter, score,
     dimensions, methodology note) is byte-identical whether diff-coverage is
     present, n/a, or absent; only the single INFO line varies. And
     :class:`GradeInputs` carries no coverage field, so the number structurally
     cannot enter the score (feeding the grade is Phase 3).
"""

from __future__ import annotations

import dataclasses
import json

from scripts.lib._control_block import format_control_block
from scripts.lib._diff_coverage_block import (
    diff_coverage_info_line,
    load_diff_coverage,
)
from scripts.lib.control_grade import DimensionResult, GradeInputs, GradeReport

_INFO_MARKER = "diff-coverage (informational"

OK_REPORT = {"status": "ok", "diff": 90.0, "total": 83.5,
             "measured_tier": "shared", "compare_branch": "origin/main"}
NA_REPORT = {"status": "n/a", "diff": None, "total": 83.5}


def _report() -> GradeReport:
    return GradeReport(
        gradeable=True, score=95.0, grade="A", verdict="Under full control.",
        band_label="Under full control.",
        dimensions=[DimensionResult(
            "test_health", "Test health", 0.20, 0.99,
            "automated tests pass (OpenSSF Scorecard)", "latest full suite 100/101")],
        reasons=[], verified_from="shipwright_events.jsonl (1 events)",
    )


# --------------------------------------------------------------------------- #
# load_diff_coverage
# --------------------------------------------------------------------------- #
class TestLoadDiffCoverage:
    def _write(self, root, payload):
        p = root / ".shipwright" / "coverage" / "diff_coverage.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload), encoding="utf-8")

    def test_absent_returns_none(self, tmp_path):
        assert load_diff_coverage(tmp_path) is None

    def test_none_root_returns_none(self):
        assert load_diff_coverage(None) is None

    def test_reads_valid_transient(self, tmp_path):
        self._write(tmp_path, OK_REPORT)
        assert load_diff_coverage(tmp_path) == OK_REPORT

    def test_malformed_json_returns_none(self, tmp_path):
        p = tmp_path / ".shipwright" / "coverage" / "diff_coverage.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{not json", encoding="utf-8")
        assert load_diff_coverage(tmp_path) is None

    def test_non_dict_returns_none(self, tmp_path):
        p = tmp_path / ".shipwright" / "coverage" / "diff_coverage.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("[1, 2]", encoding="utf-8")
        assert load_diff_coverage(tmp_path) is None


# --------------------------------------------------------------------------- #
# diff_coverage_info_line
# --------------------------------------------------------------------------- #
class TestInfoLine:
    def test_absent_says_not_measured(self):
        line = diff_coverage_info_line(None)
        assert _INFO_MARKER in line
        assert "not measured" in line

    def test_ok_shows_percent_and_tier(self):
        line = diff_coverage_info_line(OK_REPORT)
        assert "90.0% of changed lines covered" in line
        assert "shared tier" in line
        assert "origin/main" in line

    def test_na_says_na(self):
        line = diff_coverage_info_line(NA_REPORT)
        assert "n/a" in line
        assert "%" not in line  # never a misleading number

    def test_na_surfaces_producer_note(self):
        # Codex review SHOULD-FIX: n/a has several causes — the line must show
        # the producer's own note, not a hardcoded "no changed lines" reason.
        line = diff_coverage_info_line(
            {"status": "n/a", "diff": None, "note": "coverage.xml / diff-cover was unavailable"})
        assert "coverage.xml / diff-cover was unavailable" in line

    def test_na_without_note_has_generic_reason(self):
        line = diff_coverage_info_line({"status": "n/a", "diff": None})
        assert "n/a" in line and "no diff-coverage available" in line


# --------------------------------------------------------------------------- #
# Grade-neutrality
# --------------------------------------------------------------------------- #
class TestGradeNeutrality:
    def test_info_line_present_in_block(self):
        block = "\n".join(format_control_block(_report(), diff_coverage=OK_REPORT))
        assert "90.0% of changed lines covered" in block
        # ...but the grade itself is unchanged.
        assert "**A**" in block and "(95/100)" in block

    def test_grade_lines_identical_regardless_of_coverage(self):
        # Strip the single INFO line from each variant; everything else — the
        # letter, score, dimension rows, methodology note — must be identical.
        r = _report()
        stripped = []
        for cov in (None, OK_REPORT, NA_REPORT):
            block = format_control_block(r, diff_coverage=cov)
            stripped.append([ln for ln in block if _INFO_MARKER not in ln])
        assert stripped[0] == stripped[1] == stripped[2]

    def test_default_arg_is_backward_compatible(self):
        # Existing callers pass no diff_coverage — must still render (absent line).
        block = "\n".join(format_control_block(_report()))
        assert _INFO_MARKER in block
        assert "not measured" in block

    def test_grade_inputs_has_no_coverage_field(self):
        # Structural guarantee: the number cannot reach the score because
        # GradeInputs has nowhere to hold it.
        names = {f.name for f in dataclasses.fields(GradeInputs)}
        assert not any("coverage" in n for n in names)
        assert not any("diff" in n for n in names)

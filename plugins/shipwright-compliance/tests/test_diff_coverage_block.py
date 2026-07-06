"""Tests for the diff-coverage Test-Health line + strict grade extraction.

Guarantees:
  1. ``_diff_coverage_block`` loads the gitignored transient report and renders
     a Test-Health line (ok / n/a / absent).
  2. **Display/score decoupling** — the *rendered* Control-Grade block (letter,
     score, dimension rows, methodology note) is byte-identical for the INFO-line
     ``diff_coverage`` display arg whether present, n/a, or absent; only the
     single INFO line varies.
  3. **``gradeable_diff_percent``** — the strict extraction that feeds the score
     (roadmap **Phase 3**): only a finite, in-range [0, 100] ``diff`` with status
     ``ok`` yields a float; every other shape (n/a, NaN/inf, out-of-range, wrong
     type, missing) degrades to ``None`` → no Test-Health effect. Phase 3
     REPLACES the Phase-1 "GradeInputs carries no coverage field" guarantee: the
     field now exists but defaults ``None`` (grade-neutral unless supplied).
"""

from __future__ import annotations

import dataclasses
import json

from scripts.lib._control_block import format_control_block
from scripts.lib._diff_coverage_block import (
    diff_coverage_info_line,
    gradeable_diff_percent,
    load_diff_coverage,
)
from scripts.lib.control_grade import DimensionResult, GradeInputs, GradeReport

_INFO_MARKER = "diff-coverage (Control-Grade input"

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

    def test_tier_defaults_to_repo_when_absent(self):
        # Phase 2: the combined report is the norm, so a payload with no
        # measured_tier renders "repo tier" (not the Phase-1 "shared").
        line = diff_coverage_info_line(
            {"status": "ok", "diff": 88.0, "compare_branch": "origin/main"})
        assert "repo tier" in line

    def test_na_says_na(self):
        line = diff_coverage_info_line(NA_REPORT)
        assert "n/a" in line
        # Never a misleading coverage MEASUREMENT on n/a (the "≥80%" target in the
        # prefix is a threshold, not a measured number).
        assert "of changed lines covered" not in line

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

    def test_grade_inputs_coverage_field_defaults_neutral(self):
        # Phase 3 REPLACES the Phase-1 "no coverage field" guarantee: the field
        # now EXISTS (diff-coverage feeds Test-Health) but DEFAULTS to None →
        # grade-neutral unless a repo explicitly supplies it. That default is the
        # repo-agnostic guarantee that arbitrary repos see no grade change.
        fields = {f.name: f for f in dataclasses.fields(GradeInputs)}
        assert "diff_coverage_percent" in fields
        assert fields["diff_coverage_percent"].default is None


class TestGradeableDiffPercent:
    """Strict extraction that feeds the score (Phase 3). Untrusted local
    transient → only a finite, in-range [0, 100] ok-status number gets through."""

    def test_ok_finite_in_range(self):
        assert gradeable_diff_percent(OK_REPORT) == 90.0
        assert gradeable_diff_percent(
            {"status": "ok", "diff": 0}) == 0.0
        assert gradeable_diff_percent(
            {"status": "ok", "diff": 100}) == 100.0

    def test_na_status_is_none(self):
        assert gradeable_diff_percent(NA_REPORT) is None

    def test_absent_or_none_is_none(self):
        assert gradeable_diff_percent(None) is None
        assert gradeable_diff_percent({}) is None
        assert gradeable_diff_percent({"status": "ok"}) is None
        assert gradeable_diff_percent({"status": "ok", "diff": None}) is None

    def test_non_numeric_is_none(self):
        assert gradeable_diff_percent({"status": "ok", "diff": "90"}) is None
        assert gradeable_diff_percent({"status": "ok", "diff": True}) is None

    def test_non_finite_is_none(self):
        assert gradeable_diff_percent(
            {"status": "ok", "diff": float("nan")}) is None
        assert gradeable_diff_percent(
            {"status": "ok", "diff": float("inf")}) is None

    def test_out_of_range_is_none(self):
        assert gradeable_diff_percent({"status": "ok", "diff": -1.0}) is None
        assert gradeable_diff_percent({"status": "ok", "diff": 101.0}) is None

    def test_huge_int_does_not_overflow(self):
        # json.loads parses a giant integer token as an arbitrary-precision int;
        # it must be rejected by the range check WITHOUT reaching math.isfinite
        # (which would raise OverflowError). Untrusted transient → never a crash.
        assert gradeable_diff_percent({"status": "ok", "diff": 10 ** 400}) is None

    def test_composes_from_a_written_transient(self, tmp_path):
        # The exact chain build_grade_inputs runs: load the gitignored transient
        # file → strict-extract the gradeable percent.
        p = tmp_path / ".shipwright" / "coverage" / "diff_coverage.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"status": "ok", "diff": 62.5}), encoding="utf-8")
        assert gradeable_diff_percent(load_diff_coverage(tmp_path)) == 62.5
        # Absent transient (this repo on `main`) → None → grade unchanged.
        assert gradeable_diff_percent(load_diff_coverage(tmp_path / "empty")) is None


class TestBuildGradeInputsWiring:
    """End-to-end adapter seam: the transient file flows through
    build_grade_inputs onto GradeInputs.diff_coverage_percent."""

    def _data(self, root):
        from scripts.lib.data_collector import ComplianceData
        return ComplianceData(project_root=root)

    def test_transient_reaches_grade_inputs(self, tmp_path):
        from scripts.lib._control_block import build_grade_inputs
        p = tmp_path / ".shipwright" / "coverage" / "diff_coverage.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"status": "ok", "diff": 55.0}), encoding="utf-8")
        assert build_grade_inputs(self._data(tmp_path)).diff_coverage_percent == 55.0

    def test_absent_transient_is_none(self, tmp_path):
        from scripts.lib._control_block import build_grade_inputs
        # No transient (the steady state on `main`) → None → grade unchanged.
        assert build_grade_inputs(self._data(tmp_path)).diff_coverage_percent is None

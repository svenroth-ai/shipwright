"""Roadmap Phase 3 — diff-coverage feeds the Control-Grade Test-Health dimension.

Below `_DIFF_COV_WARN_THRESHOLD` (80%) the Test-Health score takes a moderate,
non-collapsing penalty (×0.85) and a WARN in its detail; at/above threshold it is
unchanged; `None` (the repo-agnostic default — every repo that supplies no
transient, incl. this repo on `main`) is byte-identical to pre-Phase-3.

Split out of `test_control_grade.py` to keep both test modules ≤300 LOC
(anti-ratchet discipline).
"""

from __future__ import annotations

from scripts.lib._control_block import format_control_block
from scripts.lib._grade_gate import _BROKEN_BELOW
from scripts.lib.control_grade import GradeInputs, GradeReport, compute_grade


def _all_green() -> GradeInputs:
    """Every dimension measurable and at/near full credit (suite 4343/4343 →
    Test-Health 1.0). Mirrors the fixture in test_control_grade.py."""
    return GradeInputs(
        frs_total=14, frs_covered=14,
        events_total=200, events_fr_tagged=200,
        latest_full_suite_passed=4343, latest_full_suite_total=4343,
        latest_full_suite_date="2026-06-13",
        events_with_provenance=200,
        reconciliation_measurable=True, frs_behavior_touched=10,
        frs_unreconciled=0,
        security_measurable=True, security_open_high_critical=0,
        bloat_ratchet_delta=0,
        deps_total=8, deps_unknown_license=0, deps_copyleft=0,
        verified_from="events.jsonl (200 events)",
    )


def _test_health(report: GradeReport):
    return next(d for d in report.dimensions if d.key == "test_health")


class TestDiffCoverageBlend:
    def test_none_is_grade_neutral(self):
        # The repo-agnostic default: no diff-coverage supplied → byte-identical
        # score AND detail (the guarantee for every arbitrary repo the grader
        # scores, and for this repo on `main` where no transient exists).
        base = compute_grade(_all_green())
        explicit = _all_green()
        explicit.diff_coverage_percent = None
        got = compute_grade(explicit)
        th_base, th_got = _test_health(base), _test_health(got)
        assert (th_got.score, th_got.detail) == (th_base.score, th_base.detail)
        assert (got.grade, got.score) == (base.grade, base.score)

    def test_above_threshold_no_penalty(self):
        inp = _all_green()                     # suite 4343/4343 → th 1.0
        inp.diff_coverage_percent = 92.0
        th = _test_health(compute_grade(inp))
        assert th.score == 1.0
        assert "WARN" not in th.detail
        assert "92.0%" in th.detail

    def test_exactly_at_threshold_is_not_below(self):
        inp = _all_green()
        inp.diff_coverage_percent = 80.0       # not < 80.0
        th = _test_health(compute_grade(inp))
        assert th.score == 1.0
        assert "WARN" not in th.detail

    def test_below_threshold_moderate_penalty_and_warn(self):
        inp = _all_green()
        inp.diff_coverage_percent = 60.0
        th = _test_health(compute_grade(inp))
        assert th.score == 0.85                # 1.0 × 0.85
        assert th.status == "gap"              # < 0.9 → the visible WARN marker
        assert "WARN diff-coverage 60.0% < 80%" in th.detail

    def test_boundary_formatting_never_contradicts_the_check(self):
        # 79.6 IS below 80 (WARN) and must render as 79.6, not a rounded
        # "80% < 80%" (external review: GPT #3 / Gemini). One-decimal formatting.
        inp = _all_green()
        inp.diff_coverage_percent = 79.6
        th = _test_health(compute_grade(inp))
        assert "79.6% < 80%" in th.detail
        assert "80.0% < 80%" not in th.detail

    def test_floor_never_collapses_a_passing_suite(self):
        # A passing-but-imperfect suite (0.55) penalised stays at the collapse
        # floor — diff-coverage is a WARN, never a hard block (Phase 3).
        inp = _all_green()
        inp.latest_full_suite_passed, inp.latest_full_suite_total = 55, 100
        inp.diff_coverage_percent = 10.0
        report = compute_grade(inp)
        th = _test_health(report)
        assert th.score == _BROKEN_BELOW       # 0.55×0.85=0.4675 → floored to 0.5
        assert th.score >= _BROKEN_BELOW       # never inside the F-collapse band
        assert report.grade != "F"             # and the headline is not F-capped

    def test_already_collapsed_suite_gets_no_extra_penalty(self):
        # Suite already below the floor by its OWN failure — diff-coverage adds
        # no further reduction (min() keeps the suite's own score).
        inp = _all_green()
        inp.latest_full_suite_passed, inp.latest_full_suite_total = 40, 100
        inp.diff_coverage_percent = 5.0
        th = _test_health(compute_grade(inp))
        assert th.score == 0.4                 # unchanged; the suite dominates
        assert "WARN diff-coverage" in th.detail   # still surfaced

    def test_zero_suite_stays_na_even_below_threshold(self):
        inp = _all_green()
        inp.latest_full_suite_passed = None
        inp.latest_full_suite_total = None
        inp.diff_coverage_percent = 10.0
        th = _test_health(compute_grade(inp))
        assert th.score is None
        assert th.status == "n/a"

    def test_diff_coverage_is_not_a_collapse_pillar(self):
        # Even diff-coverage 0% on a green suite only trims ~3 headline points
        # (0.15 × 0.20 weight); it must NOT hard-cap into F (that is Phase 4).
        inp = _all_green()
        inp.diff_coverage_percent = 0.0
        assert compute_grade(inp).grade == "A"

    def test_dashboard_renders_warn_text(self):
        inp = _all_green()
        inp.diff_coverage_percent = 60.0
        report = compute_grade(inp)
        assert _test_health(report).status == "gap"
        block = "\n".join(format_control_block(report))
        assert "WARN diff-coverage 60.0% < 80%" in block

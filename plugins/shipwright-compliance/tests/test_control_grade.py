"""Tests for control_grade.py — the deterministic Control Grade scorer.

Outcome-focused: bands, the OpenSSF-Scorecard-style N/A exclusion, the
all-N/A "Not Gradeable" guard, determinism, and the requirement-traceability
freeze case (the honest cap on this repo).
"""

from __future__ import annotations

from types import SimpleNamespace

from scripts.lib._control_block import format_control_block
from scripts.lib._latest_suite import resolve_latest_full_suite
from scripts.lib.control_grade import (
    GradeInputs,
    GradeReport,
    _band,
    compute_grade,
)


def _ev(passed: int, total: int, ts: str):
    return SimpleNamespace(tests_passed=passed, tests_total=total, timestamp=ts)


class TestLatestSuiteResolver:
    """AR-02: resolve the latest *full* suite, not the last event."""

    def test_skips_trailing_zero_and_subset_events(self):
        evs = [
            _ev(3473, 3473, "2026-06-14T09:00:00+00:00"),
            _ev(0, 0, "2026-06-15T00:00:00+00:00"),      # doc commit
            _ev(94, 94, "2026-06-16T00:00:00+00:00"),    # subset < 50% of max
        ]
        s = resolve_latest_full_suite(evs)
        assert (s.passed, s.total, s.date) == (3473, 3473, "2026-06-14")
        assert s.changes_since == 2  # the 0/0 + the subset run after it

    def test_none_when_no_tests_ever(self):
        assert resolve_latest_full_suite(
            [_ev(0, 0, "2026-06-14T00:00:00+00:00")]) is None

    def test_picks_most_recent_full_suite_not_the_max(self):
        # Two full suites; the more recent (3473) wins over the larger
        # earlier peak (4343) — the exact AR-02 correction.
        evs = [
            _ev(4343, 4343, "2026-06-13T10:00:00+00:00"),
            _ev(3473, 3473, "2026-06-14T09:00:00+00:00"),
        ]
        s = resolve_latest_full_suite(evs)
        assert (s.total, s.date) == (3473, "2026-06-14")


def _all_green() -> GradeInputs:
    """A repo with every dimension measurable and at/near full credit."""
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


class TestBands:
    def test_all_green_is_A(self):
        report = compute_grade(_all_green())
        assert report.gradeable is True
        assert report.grade == "A"
        assert report.score >= 90.0
        assert report.verdict.startswith("Under full control.")

    def test_band_thresholds_are_inclusive(self):
        # 90 → A, 80 → B, 70 → C, 50 → D, below → F (boundary inclusive).
        from scripts.lib.control_grade import _band
        assert _band(90.0)[0] == "A"
        assert _band(89.9)[0] == "B"
        assert _band(80.0)[0] == "B"
        assert _band(70.0)[0] == "C"
        assert _band(50.0)[0] == "D"
        assert _band(49.9)[0] == "F"


class TestNaExclusion:
    def test_missing_full_suite_is_na_not_zero(self):
        inp = _all_green()
        inp.latest_full_suite_passed = None
        inp.latest_full_suite_total = None
        report = compute_grade(inp)
        test_health = next(
            d for d in report.dimensions if d.key == "test_health")
        assert test_health.score is None
        assert test_health.status == "n/a"
        # Excluded from the denominator → the remaining all-green dims keep A.
        assert report.grade == "A"

    def test_missing_security_excluded_from_denominator(self):
        inp = _all_green()
        inp.security_measurable = False
        inp.security_open_high_critical = None
        report = compute_grade(inp)
        sec = next(d for d in report.dimensions if d.key == "security")
        assert sec.score is None
        # A dimension scored None must not drag the score the way a 0 would.
        assert report.score >= 90.0

    def test_reconciliation_na_until_bp2(self):
        inp = _all_green()
        inp.reconciliation_measurable = False
        report = compute_grade(inp)
        rec = next(
            d for d in report.dimensions if d.key == "change_reconciliation")
        assert rec.score is None
        assert "BP-2" in rec.detail

    def test_reconciliation_scored_when_measurable(self):
        inp = _all_green()
        inp.reconciliation_measurable = True
        inp.frs_behavior_touched = 10
        inp.frs_unreconciled = 5
        report = compute_grade(inp)
        rec = next(
            d for d in report.dimensions if d.key == "change_reconciliation")
        assert rec.score == 0.5


class TestNotGradeable:
    def test_all_na_is_not_gradeable_never_F(self):
        # Empty repo: nothing measurable anywhere.
        report = compute_grade(GradeInputs())
        assert report.gradeable is False
        assert report.grade == "?"
        assert report.score is None
        assert "Not gradeable" in report.verdict
        # Critically: NOT an unearned F.
        assert report.grade != "F"


class TestFreezeCase:
    def test_freeze_is_visible_even_when_everything_else_perfect(self):
        """A total FR-tag freeze renders the dimension as a gap + a reason."""
        inp = _all_green()
        inp.events_fr_tagged = 0  # total freeze
        report = compute_grade(inp)
        req = next(
            d for d in report.dimensions
            if d.key == "requirement_traceability")
        assert req.status == "gap"
        assert any("Requirement traceability" in r for r in report.reasons)

    def test_real_shipwright_case_grades_B(self):
        """The honest current grade: covered FRs, frozen tagging, recon +
        security n/a (BP-2 unbuilt / no trustworthy local scan), SBOM dings.
        Caps at B — 'controlled, minor gaps' — not A, not a false F."""
        inp = GradeInputs(
            frs_total=14, frs_covered=14,
            events_total=209, events_fr_tagged=52,
            latest_full_suite_passed=3473, latest_full_suite_total=3473,
            latest_full_suite_date="2026-06-14",
            events_with_provenance=209,
            reconciliation_measurable=False,
            security_measurable=False, security_open_high_critical=None,
            bloat_ratchet_delta=0,
            deps_total=8, deps_unknown_license=4, deps_copyleft=0,
        )
        report = compute_grade(inp)
        assert report.grade == "B"
        na = {d.key for d in report.dimensions if d.status == "n/a"}
        assert na == {"change_reconciliation", "security"}
        req = next(
            d for d in report.dimensions
            if d.key == "requirement_traceability")
        assert req.status == "gap"
        assert any("Requirement traceability" in r for r in report.reasons)


class TestDeterminismAndShape:
    def test_same_inputs_same_grade(self):
        a = compute_grade(_all_green())
        b = compute_grade(_all_green())
        assert (a.grade, a.score, a.verdict) == (b.grade, b.score, b.verdict)

    def test_verdict_maps_to_band_no_freetext(self):
        report = compute_grade(_all_green())
        # Verdict always begins with the canonical band label.
        assert report.verdict.startswith("Under full control.")

    def test_every_dimension_has_an_anchor(self):
        report = compute_grade(_all_green())
        assert len(report.dimensions) == 7
        assert all(d.anchor for d in report.dimensions)

    def test_displayed_int_never_contradicts_letter_at_boundary(self):
        # The :.0f-round bug would render '90/100' next to a 'B' at score 89.9.
        report = GradeReport(
            gradeable=True, score=89.9, grade="B",
            verdict="Controlled, minor gaps.",
            band_label="Controlled, minor gaps.",
            dimensions=[], reasons=[], verified_from="x",
        )
        block = "\n".join(format_control_block(report))
        assert "**B**" in block
        assert "(89/100)" in block
        assert "(90/100)" not in block

    def test_floored_score_shares_band_with_letter(self):
        # int(score) must land in the same band as the precise score, for every
        # 0.1 step — the property that makes the floored display safe.
        for s10 in range(0, 1001):
            s = s10 / 10.0
            assert _band(int(s))[0] == _band(s)[0]

    def test_garbage_inputs_stay_in_range(self):
        # Out-of-range adapter inputs must not push the score outside [0, 100].
        inp = _all_green()
        inp.security_open_high_critical = -5  # nonsense
        inp.deps_copyleft = -3
        report = compute_grade(inp)
        assert 0.0 <= report.score <= 100.0

    def test_reasons_capped_at_three(self):
        inp = _all_green()
        # Make several dimensions imperfect.
        inp.events_fr_tagged = 10
        inp.latest_full_suite_passed = 3000  # < total
        inp.deps_unknown_license = 4
        inp.bloat_ratchet_delta = 50
        inp.security_open_high_critical = 2
        report = compute_grade(inp)
        assert len(report.reasons) <= 3

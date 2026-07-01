"""Tests for the Control-Grade honesty layer (_grade_gate) + the anchor pivot.

Covers the two Goodhart-resistance caps kept in the verdict gate — the
dark-expected cap and the broken-pillar cap — plus the de-crowded,
safety-critical-free anchors. Workload composition (feature vs. maintenance mix)
is deliberately **grade-neutral**: it is no longer a GradeInputs field and never
caps or penalises the score. The composition-neutral quality-indicator row is
covered in test_traceability.py; the pure scorer's back-compat (no signal ⇒
unchanged) is asserted in test_control_grade.py.
"""

from __future__ import annotations

from scripts.lib._grade_gate import (
    BROKEN_PILLAR_CEILING,
    NON_A_CEILING,
    apply_verdict_gate,
)
from scripts.lib.control_grade import GradeInputs, compute_grade


def _green(**over) -> GradeInputs:
    """Every dimension measurable and at full credit; override per test."""
    base = dict(
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
    base.update(over)
    return GradeInputs(**base)


def _dim(report, key):
    return next(d for d in report.dimensions if d.key == key)


class TestPerfectRepoIsA:
    def test_perfect_repo_is_A(self):
        report = compute_grade(_green())
        assert report.grade == "A"
        assert report.score >= 90.0
        assert "Capped" not in report.verdict


class TestVerdictGateDarkExpected:
    def test_expected_but_dark_security_caps_and_flags_incomplete(self):
        report = compute_grade(_green(
            security_measurable=False, security_open_high_critical=None,
            expected_dimensions=("security",)))
        assert _dim(report, "security").status == "n/a"
        assert report.grade == "B"
        assert report.score <= NON_A_CEILING
        assert "verification incomplete" in report.verdict
        assert "security" in report.verdict

    def test_dark_but_not_expected_stays_A(self):
        # Back-compat: with no expectation a missing pillar is just excluded.
        report = compute_grade(_green(
            security_measurable=False, security_open_high_critical=None))
        assert report.grade == "A"


class TestVerdictGateBrokenPillar:
    def test_broken_load_bearing_pillar_caps_to_F(self):
        report = compute_grade(
            _green(latest_full_suite_passed=40, latest_full_suite_total=100))
        assert report.grade == "F"
        assert report.score <= BROKEN_PILLAR_CEILING
        assert "failing" in report.verdict

    def test_broken_supporting_dim_does_not_hard_cap(self):
        # Dependency hygiene is NOT load-bearing: a 0-score there is a gap that
        # the average reflects, but it must not weakest-link the headline to F.
        report = compute_grade(_green(deps_total=8, deps_unknown_license=8))
        assert _dim(report, "dependency_hygiene").score == 0.0
        assert report.grade == "A"  # 0.05*0 off a 1.0 base → 95 → still A

    def test_low_requirement_traceability_is_a_gap_not_an_F(self):
        # requirement_traceability is deliberately NOT a collapse pillar: poor
        # coverage/tagging drops its score AND the weighted average, but it must
        # never weakest-link the headline to F (only test/provenance/security do).
        report = compute_grade(_green(
            frs_total=14, frs_covered=1, events_total=200, events_fr_tagged=20))
        assert _dim(report, "requirement_traceability").score < 0.5
        assert report.grade != "F"

    def test_one_open_critical_is_a_gap_not_a_hard_cap(self):
        # A single high/critical scores the security dim ~0.66 (>= 0.5) → it is a
        # gap shaped by the average, not a broken-pillar F-cap.
        report = compute_grade(_green(security_open_high_critical=1))
        sec = _dim(report, "security")
        assert 0.5 <= sec.score < 0.9
        assert report.grade in ("A", "B")


class TestGateReturnShape:
    def test_no_conditions_returns_raw_ceiling(self):
        inp = _green()
        report = compute_grade(inp)
        ceiling, reasons = apply_verdict_gate(inp, report.dimensions, 100.0)
        assert ceiling == 100.0
        assert reasons == []


class TestAnchorPivot:
    RETIRED = ("DO-178C", "DO178C", "IEC 62304", "ISO 26262")

    def test_no_safety_critical_certification_standard(self):
        for d in compute_grade(_green()).dimensions:
            for std in self.RETIRED:
                assert std not in d.anchor, f"{d.key}: {std} still in {d.anchor!r}"

    def test_each_anchor_cites_a_single_standard(self):
        # De-crowd: exactly one open standard per Anchor (no "(A, B)" lists).
        for d in compute_grade(_green()).dimensions:
            inside = d.anchor[d.anchor.find("(") + 1:d.anchor.rfind(")")]
            assert "," not in inside, f"{d.key}: multi-standard anchor {d.anchor!r}"

    def test_pivoted_anchors_are_present(self):
        anchors = {d.key: d.anchor for d in compute_grade(_green()).dimensions}
        assert "ISO/IEC/IEEE 29148" in anchors["requirement_traceability"]
        assert "ISO/IEC/IEEE 12207" in anchors["change_reconciliation"]
        assert "NIST SSDF" in anchors["security"]

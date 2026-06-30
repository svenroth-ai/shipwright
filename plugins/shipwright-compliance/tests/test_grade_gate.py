"""Tests for the Control-Grade honesty layer (_grade_gate) + the anchor pivot.

Covers the three Goodhart-resistance mechanisms — the self-relative traceability
decline penalty, and the weakest-link verdict gate (decline cap / dark-expected
cap / broken-pillar cap) — plus the de-crowded, safety-critical-free anchors.
The pure scorer's back-compat (no signal ⇒ unchanged) is asserted in
test_control_grade.py; here we light the new signals explicitly.
"""

from __future__ import annotations

from scripts.lib._grade_gate import (
    BROKEN_PILLAR_CEILING,
    NON_A_CEILING,
    apply_verdict_gate,
    trace_decline_severity,
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


class TestDeclineSeverity:
    def test_no_signal_is_zero(self):
        assert trace_decline_severity(_green()) == 0.0

    def test_total_freeze_is_one(self):
        assert trace_decline_severity(
            _green(fr_tag_recent_pct=0.0, fr_tag_all_pct=0.18)) == 1.0

    def test_relative_drop_is_fractional(self):
        sev = trace_decline_severity(
            _green(fr_tag_recent_pct=0.03, fr_tag_all_pct=0.18))
        assert 0.8 < sev < 0.84  # (0.18-0.03)/0.18 ≈ 0.833

    def test_stable_low_is_not_a_decline(self):
        # recent == all-time (steadily low) is NOT erosion → no penalty.
        assert trace_decline_severity(
            _green(fr_tag_recent_pct=0.05, fr_tag_all_pct=0.05)) == 0.0

    def test_improvement_is_not_a_decline(self):
        assert trace_decline_severity(
            _green(fr_tag_recent_pct=0.30, fr_tag_all_pct=0.18)) == 0.0


class TestTraceabilityPenalty:
    def test_decline_depresses_requirement_dimension(self):
        report = compute_grade(
            _green(fr_tag_recent_pct=0.03, fr_tag_all_pct=0.18))
        req = _dim(report, "requirement_traceability")
        assert req.score < 1.0
        assert req.status == "gap"
        assert "declining" in req.detail

    def test_penalty_is_capped_not_zeroing(self):
        # A full freeze removes at most TRACE_DECLINE_MAX_PENALTY (0.35) of a
        # dimension that was otherwise 1.0 → floors at 0.65, never 0.
        report = compute_grade(
            _green(fr_tag_recent_pct=0.0, fr_tag_all_pct=0.20))
        req = _dim(report, "requirement_traceability")
        assert abs(req.score - 0.65) < 1e-9

    def test_no_signal_leaves_dimension_intact(self):
        req = _dim(compute_grade(_green()), "requirement_traceability")
        assert req.score == 1.0


class TestVerdictGateDecline:
    def test_decline_caps_headline_below_A(self):
        report = compute_grade(
            _green(fr_tag_recent_pct=0.03, fr_tag_all_pct=0.18))
        assert report.grade == "B"
        assert report.score <= NON_A_CEILING
        assert int(report.score) == 89  # score+letter stay consistent
        assert "Capped" in report.verdict
        assert "declining" in report.verdict

    def test_perfect_repo_without_decline_is_A(self):
        report = compute_grade(_green())
        assert report.grade == "A"
        assert report.score >= 90.0

    def test_nonbinding_decline_does_not_claim_capped(self):
        # raw already below the 89 ceiling → the decline cap isn't binding, so the
        # verdict must NOT say "Capped:"; the decline still surfaces via the
        # requirement dimension's detail.
        report = compute_grade(_green(
            frs_total=14, frs_covered=7, events_total=200, events_fr_tagged=100,
            fr_tag_recent_pct=0.03, fr_tag_all_pct=0.18, fr_tag_window=30))
        assert report.score < 89.0
        assert "Capped:" not in report.verdict
        assert any("declining" in r for r in report.reasons)


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

    def test_decline_penalty_never_triggers_the_F_collapse_cap(self):
        # Regression (review #1): a steep decline penalty can drag an otherwise
        # healthy requirement dimension below 0.5, but traceability erosion is a
        # *decline* (cap B), NEVER a verifiability *collapse* (cap F). req_pre =
        # 0.6*1.0 + 0.4*0.25 = 0.70 → penalised ~0.496 (< 0.5) yet must not F-cap.
        report = compute_grade(_green(
            events_total=200, events_fr_tagged=50,  # tag_rate 0.25 → req_pre 0.70
            fr_tag_recent_pct=0.03, fr_tag_all_pct=0.18, fr_tag_window=30))
        assert _dim(report, "requirement_traceability").score < 0.5
        assert report.grade != "F"
        assert report.grade in ("B", "C")

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

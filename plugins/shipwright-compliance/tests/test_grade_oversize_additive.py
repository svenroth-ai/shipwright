"""Golden-regression gate for the additive ``oversize_file_ratio`` field (G2).

The engine change is **additive-only** (plan §8): a cold repo with no ratchet
baseline may score dimension 6 from a static oversize-file ratio, but the
scorer's behaviour for **every existing input** is byte-identical. These tests
pin that invariant:

- ratchet path wins and is unaffected when ``oversize_file_ratio`` is also set;
- the no-baseline path keeps its exact score / detail / **anchor** (the "before"
  values, proving the new field is inert for existing callers — the dashboard
  always sets ``bloat_ratchet_delta`` and never ``oversize_file_ratio``);
- the new branch lights only when ``bloat_ratchet_delta is None`` and renders an
  honest, distinct detail + anchor (not a faked ratchet delta).
"""

from __future__ import annotations

import dataclasses

from scripts.lib.control_grade import GradeInputs, compute_grade


def _measurable_base(**overrides) -> GradeInputs:
    """A repo with several measurable dims so dim 6 actually moves the grade."""
    base = dict(
        frs_total=10, frs_covered=9,
        events_total=100, events_fr_tagged=95,
        events_with_provenance=100,
        latest_full_suite_passed=200, latest_full_suite_total=200,
        latest_full_suite_date="2026-07-01",
        security_measurable=True, security_open_high_critical=0,
        deps_total=20, deps_unknown_license=0, deps_copyleft=0,
        verified_from="test",
    )
    base.update(overrides)
    return GradeInputs(**base)


def _maint(report):
    return next(d for d in report.dimensions if d.key == "maintainability")


class TestAdditiveIsolation:
    """The dashboard/cert path (ratchet set) is byte-identical with the field."""

    def test_ratchet_report_unchanged_when_oversize_also_set(self):
        ratchet_only = _measurable_base(bloat_ratchet_delta=0)
        ratchet_plus = _measurable_base(bloat_ratchet_delta=0, oversize_file_ratio=0.9)
        # Ratchet wins; the whole report is byte-identical regardless of the new field.
        assert (dataclasses.asdict(compute_grade(ratchet_only))
                == dataclasses.asdict(compute_grade(ratchet_plus)))

    def test_ratchet_growth_detail_and_anchor_preserved(self):
        r = compute_grade(_measurable_base(bloat_ratchet_delta=25))
        m = _maint(r)
        assert m.score == 0.75  # 1 - 25/100
        assert m.detail == "ratchet delta +25 lines (net growth)"
        assert m.anchor == "no unchecked code-size growth (ISO/IEC 25010)"


class TestNoBaselineByteIdentity:
    """Both size signals None → the exact pre-field maintainability n/a result."""

    def test_no_baseline_is_na_with_frozen_detail_and_anchor(self):
        m = _maint(compute_grade(_measurable_base()))  # neither size signal set
        assert m.score is None
        assert m.status == "n/a"
        assert m.detail == "no size baseline"
        assert m.anchor == "no unchecked code-size growth (ISO/IEC 25010)"

    def test_full_report_byte_identical_snapshot(self):
        """True golden (external review GPT #2): the ENTIRE serialized GradeReport
        for a canonical dashboard-like fixture (``oversize_file_ratio=None``) is
        pinned byte-for-byte, so ANY drift in a score, precision, detail, anchor,
        reason or verdict — not just the maintainability dim — fails the gate."""
        expected = {
            "gradeable": True, "score": 97.3, "grade": "A",
            "verdict": "Under full control. Primarily capped by requirement traceability.",
            "band_label": "Under full control.",
            "dimensions": [
                {"key": "requirement_traceability", "label": "Requirement traceability",
                 "weight": 0.25, "score": 0.92,
                 "anchor": "requirement-to-work traceability (ISO/IEC/IEEE 29148)",
                 "detail": "9/10 FRs covered; 95/100 changes traced "
                           "(FR-linked or classified no-FR)"},
                {"key": "test_health", "label": "Test health", "weight": 0.2,
                 "score": 1.0, "anchor": "automated tests pass (OpenSSF Scorecard)",
                 "detail": "latest full suite 200/200 (2026-07-01)"},
                {"key": "change_traceability", "label": "Change traceability",
                 "weight": 0.15, "score": 1.0, "anchor": "change provenance (SLSA)",
                 "detail": "100/100 changes linked to a commit, ADR or test run"},
                {"key": "change_reconciliation", "label": "Change reconciliation",
                 "weight": 0.15, "score": None,
                 "anchor": "re-verify changed requirements (ISO/IEC/IEEE 12207)",
                 "detail": "not measurable — needs per-change behavior-impact (BP-2)"},
                {"key": "security", "label": "Security", "weight": 0.1, "score": 1.0,
                 "anchor": "no open high/critical vulns (NIST SSDF)",
                 "detail": "0 open high/critical"},
                {"key": "maintainability", "label": "Size / maintainability discipline",
                 "weight": 0.1, "score": None,
                 "anchor": "no unchecked code-size growth (ISO/IEC 25010)",
                 "detail": "no size baseline"},
                {"key": "dependency_hygiene", "label": "Dependency hygiene",
                 "weight": 0.05, "score": 1.0,
                 "anchor": "dependency license & risk (OWASP)",
                 "detail": "0 unresolved / 20 licenses; 0 copyleft"},
            ],
            "reasons": ["Requirement traceability: 9/10 FRs covered; "
                        "95/100 changes traced (FR-linked or classified no-FR)"],
            "verified_from": "test",
        }
        assert dataclasses.asdict(compute_grade(_measurable_base())) == expected


class TestNewOversizeBranch:
    """The additive branch lights only when there is no ratchet baseline."""

    def test_oversize_only_is_scored_with_distinct_detail_and_anchor(self):
        m = _maint(compute_grade(_measurable_base(oversize_file_ratio=0.2)))
        assert m.score == 0.8  # 1 - 0.2
        assert m.detail == "20% of source files over the size threshold"
        assert m.anchor == "bounded module size (ISO/IEC 25010)"
        assert "ratchet" not in m.detail  # never a faked ratchet delta

    def test_oversize_ratio_is_clamped(self):
        assert _maint(compute_grade(_measurable_base(oversize_file_ratio=1.5))).score == 0.0
        assert _maint(compute_grade(_measurable_base(oversize_file_ratio=-0.5))).score == 1.0

    def test_zero_oversize_is_full_credit(self):
        m = _maint(compute_grade(_measurable_base(oversize_file_ratio=0.0)))
        assert m.score == 1.0
        assert m.detail == "0% of source files over the size threshold"

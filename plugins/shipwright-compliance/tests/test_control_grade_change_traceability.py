"""Change-traceability measurability gate (engine-level).

``change_traceability`` scores off ``events_with_provenance`` ONLY when the
provenance is trustworthy — real event-log records (the authoritative dashboard)
or the network PR-association ratio (the cold grader with ``--allow-network``).
The cold-repo local-only path sets ``change_traceability_measurable=False``: its
only signal is git-log ``#N`` references, which anti-correlate with quality, so
the dimension renders n/a rather than scoring (or F-collapsing on) a misleading
proxy — mirroring how test-health/security degrade to n/a without a trustworthy
signal. The engine default is True so every existing (authoritative) caller is
byte-identical; only the cold grader opts out.
"""

from __future__ import annotations

from types import SimpleNamespace

from scripts.lib._control_block import build_grade_inputs
from scripts.lib.control_grade import GradeInputs, compute_grade


def _all_green() -> GradeInputs:
    """Every dimension measurable and at/near full credit (change_trace = 200/200)."""
    return GradeInputs(
        frs_total=14, frs_covered=14,
        events_total=200, events_fr_tagged=200,
        latest_full_suite_passed=4343, latest_full_suite_total=4343,
        latest_full_suite_date="2026-06-13",
        events_with_provenance=200,
        reconciliation_measurable=True, frs_behavior_touched=10, frs_unreconciled=0,
        security_measurable=True, security_open_high_critical=0,
        bloat_ratchet_delta=0,
        deps_total=8, deps_unknown_license=0, deps_copyleft=0,
    )


class TestChangeTraceabilityGate:
    def test_default_is_measurable(self):
        # Default True → every existing engine caller (dashboard, tests) unchanged.
        assert GradeInputs().change_traceability_measurable is True

    def test_scored_when_measurable(self):
        report = compute_grade(_all_green())
        ct = next(d for d in report.dimensions if d.key == "change_traceability")
        assert ct.score == 1.0  # 200/200
        assert ct.status == "ok"

    def test_na_when_not_measurable(self):
        inp = _all_green()
        inp.change_traceability_measurable = False
        report = compute_grade(inp)
        ct = next(d for d in report.dimensions if d.key == "change_traceability")
        assert ct.score is None
        assert ct.status == "n/a"
        assert "allow-network" in ct.detail

    def test_not_measurable_excluded_from_denominator_keeps_A(self):
        # n/a (not 0) → excluded from the weighted average, so the remaining
        # all-green dims still grade A. The proof that this is n/a, not a 0/gap.
        inp = _all_green()
        inp.change_traceability_measurable = False
        report = compute_grade(inp)
        assert report.grade == "A"

    def test_not_measurable_never_f_collapses_on_reference_free_repo(self):
        # The shitstorm root cause at the engine seam: with 0 provenance events and
        # measurable=False, change_traceability must NOT collapse the headline to F
        # (it is a _COLLAPSE_PILLAR only when *scored* < 0.5). n/a excludes it.
        inp = _all_green()
        inp.change_traceability_measurable = False
        inp.events_with_provenance = 0
        report = compute_grade(inp)
        ct = next(d for d in report.dimensions if d.key == "change_traceability")
        assert ct.status == "n/a"
        assert report.grade == "A"  # not F

    def test_measurable_but_no_events_is_na(self):
        # measurable=True but no change events recorded → still n/a (nothing to
        # score), with the distinct "no change events" detail, not the network one.
        inp = _all_green()
        inp.events_total = 0
        inp.events_with_provenance = 0
        report = compute_grade(inp)
        ct = next(d for d in report.dimensions if d.key == "change_traceability")
        assert ct.score is None
        assert "no change events" in ct.detail


class TestAuthoritativeAdapterKeepsItMeasurable:
    """The compliance adapter (dashboard + grade-plugin authoritative path) grades
    from real event-log provenance, so it sets the flag True explicitly. This locks
    that intent: a future default flip to False would otherwise silently dark the
    dashboard's AND the authoritative grade's change-traceability pillar."""

    def _data(self, project_root):
        return SimpleNamespace(
            work_events=[], requirements=[], dependencies=[],
            project_root=project_root)

    def test_adapter_sets_change_traceability_measurable_true(self, tmp_path):
        inp = build_grade_inputs(self._data(tmp_path))
        assert inp.change_traceability_measurable is True

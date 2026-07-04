"""Tests for signal_bundle — the mapping from G2 signals onto the engine surface."""

from __future__ import annotations

from dependency_signal import DependencySignal
from security_signal import SecuritySignal
from signal_bundle import SignalBundle
from size_signal import SizeSignal
from test_health_signal import TestHealthSignal


def _lit_bundle() -> SignalBundle:
    return SignalBundle(
        test_health=TestHealthSignal(True, 90, 100, "ci-junit", "latest CI suite 90/100"),
        security=SecuritySignal(True, 2, "2 open high/critical (code-scanning)",
                                "github-code-scanning"),
        dependency=DependencySignal(True, 10, 1, 0, "1/10 undeclared; 0 copyleft", 3),
        size=SizeSignal(True, 0.2, 2, 10, "2/10 source files over 300 LOC", False),
    )


def _na_bundle() -> SignalBundle:
    return SignalBundle(
        test_health=TestHealthSignal(False, None, None, "static-inventory", "no ratio"),
        security=SecuritySignal(False, None, "no code-scanning ingested (local-only)", ""),
        dependency=DependencySignal(False, 0, 0, 0, "no dependency manifest", 0),
        size=SizeSignal(False, None, 0, 0, "no source files to size", False),
    )


class TestGradeInputKwargs:
    def test_lit_bundle_maps_every_field(self):
        kw = _lit_bundle().grade_input_kwargs()
        assert kw == {
            "oversize_file_ratio": 0.2,
            "latest_full_suite_passed": 90, "latest_full_suite_total": 100,
            "security_measurable": True, "security_open_high_critical": 2,
            "deps_total": 10, "deps_unknown_license": 1, "deps_copyleft": 0,
        }

    def test_na_bundle_sets_nothing(self):
        # Every n/a signal keeps the engine's own n/a default (empty kwargs).
        assert _na_bundle().grade_input_kwargs() == {}


class TestDetailOverrides:
    def test_lit_bundle_labels_scored_test_health(self):
        ov = _lit_bundle().detail_overrides()
        assert ov["test_health"] == "latest CI suite 90/100"
        assert ov["security"] == "2 open high/critical (code-scanning)"
        assert ov["maintainability"] == "2/10 source files over 300 LOC"
        assert ov["dependency_hygiene"] == "1/10 undeclared; 0 copyleft"

    def test_na_test_health_not_overridden(self):
        # A static-inventory (n/a) test-health leaves the projector's line intact.
        assert "test_health" not in _na_bundle().detail_overrides()


class TestProvenance:
    def test_lit_dims_clear_disabled_enrichments(self):
        prov = _lit_bundle().provenance()
        assert "ci-junit" in prov["test_health"]["source"]
        assert prov["security"]["disabled"] == ()
        assert prov["maintainability"]["disabled"] == ()

    def test_na_dims_name_disabled_enrichments(self):
        prov = _na_bundle().provenance()
        assert prov["security"]["disabled"] == ("code-scanning-sarif",)
        assert prov["dependency_hygiene"]["disabled"] == ("lockfile-sbom",)
        assert prov["test_health"]["disabled"]  # non-empty

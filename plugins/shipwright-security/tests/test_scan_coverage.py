"""Tests for the scan coverage manifest (``scan_coverage``).

AC-1 / AC-2 of iterate-2026-07-27-security-coverage-manifest: a scan records
one row per weakness class so a machine with one tool cannot produce a report
that reads clean for every class.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from scan_coverage import (  # noqa: E402
    CLASS_ORDER,
    COVERAGE_STATUSES,
    PROMPT_INJECTION_CLASS,
    build_coverage,
    covered_classes,
    finding_class,
    is_complete,
    unchecked_classes,
    with_prompt_injection_row,
)


def _status_of(coverage: list[dict], cls: str) -> str:
    return next(row["status"] for row in coverage if row["class"] == cls)


@pytest.mark.covers("FR-01.07")
class TestBuildCoverage:
    def test_every_class_gets_a_row_even_with_no_tools(self) -> None:
        """The invisible case: nothing installed must not yield an empty
        manifest — it must yield three explicit `not_available` rows."""
        coverage = build_coverage(available=set())
        assert [row["class"] for row in coverage] == list(CLASS_ORDER)
        assert {row["status"] for row in coverage} == {"not_available"}

    def test_one_installed_tool_names_the_other_two(self) -> None:
        coverage = build_coverage(available={"sast"})
        assert _status_of(coverage, "sast") == "covered"
        assert _status_of(coverage, "sca") == "not_available"
        assert _status_of(coverage, "secrets") == "not_available"
        assert unchecked_classes(coverage) == ["sca", "secrets"]
        assert is_complete(coverage) is False

    def test_all_tools_present_is_complete(self) -> None:
        coverage = build_coverage(available={"sast", "sca", "secrets"})
        assert covered_classes(coverage) == {"sast", "sca", "secrets"}
        assert unchecked_classes(coverage) == []
        assert is_complete(coverage) is True

    def test_not_requested_beats_not_available(self) -> None:
        """A class the caller scoped out reads `not_requested`, not
        `not_available` — the operator asked for a narrower scan, they did
        not hit a missing tool."""
        coverage = build_coverage(available={"sast"}, requested=["sast"])
        assert _status_of(coverage, "sca") == "not_requested"
        assert _status_of(coverage, "secrets") == "not_requested"

    def test_degraded_leg_beats_every_other_status(self) -> None:
        """A recorded scan_error is hard evidence the leg ran and failed —
        it must not be masked as `not_available` when the binary vanished
        mid-run and the capability re-probe therefore comes back empty."""
        coverage = build_coverage(
            available=set(),
            scan_errors=[
                {"scanner": "gitleaks", "reason": "missing_binary",
                 "detail": "binary not found on PATH"},
            ],
        )
        secrets = next(r for r in coverage if r["class"] == "secrets")
        assert secrets["status"] == "degraded"
        assert "missing_binary" in secrets["detail"]

    def test_not_available_detail_names_the_missing_tool(self) -> None:
        coverage = build_coverage(available={"sca", "secrets"})
        sast = next(r for r in coverage if r["class"] == "sast")
        assert sast["tool"] == "semgrep"
        assert "semgrep" in sast["detail"]

    def test_capability_outside_the_oss_tool_map_still_gets_a_row(self) -> None:
        """Aikido offers `iac`; a class with no local tool must appear rather
        than be silently dropped."""
        coverage = build_coverage(available={"sast", "sca", "secrets", "iac"})
        iac = next(r for r in coverage if r["class"] == "iac")
        assert iac["status"] == "covered"
        assert iac["tool"] is None

    def test_a_case_variant_capability_does_not_duplicate_a_class(self) -> None:
        """A backend advertising 'SAST' must not add a second row alongside the
        'sast' one CLASS_ORDER already emits — two rows for one logical class
        would let the manifest disagree with itself about what was checked."""
        coverage = build_coverage(available={"SAST", "sca", "secrets"})
        classes = [r["class"] for r in coverage]
        assert classes == list(CLASS_ORDER), classes
        assert _status_of(coverage, "sast") == "covered"

    def test_a_case_variant_requested_type_still_matches(self) -> None:
        coverage = build_coverage(available={"sast"}, requested=["SAST"])
        assert _status_of(coverage, "sast") == "covered"

    def test_every_status_is_in_the_closed_vocabulary(self) -> None:
        coverage = build_coverage(
            available={"sast"},
            requested=["sast", "sca"],
            scan_errors=[{"scanner": "semgrep", "reason": "timeout", "detail": "x"}],
        )
        assert all(row["status"] in COVERAGE_STATUSES for row in coverage)

    def test_rows_are_json_serializable_scalars(self) -> None:
        """The manifest rides in findings.json — no sets, no Paths."""
        import json
        coverage = build_coverage(available={"sast"})
        assert json.loads(json.dumps(coverage)) == coverage


@pytest.mark.covers("FR-01.07")
class TestPromptInjectionRow:
    def test_row_is_appended_as_not_requested_when_scan_did_not_run(self) -> None:
        coverage = with_prompt_injection_row(build_coverage(available=set()), ran=False)
        assert _status_of(coverage, PROMPT_INJECTION_CLASS) == "not_requested"

    def test_row_is_covered_when_prompt_risks_were_merged(self) -> None:
        coverage = with_prompt_injection_row(build_coverage(available=set()), ran=True)
        assert _status_of(coverage, PROMPT_INJECTION_CLASS) == "covered"

    def test_existing_row_is_not_duplicated(self) -> None:
        once = with_prompt_injection_row([], ran=True)
        twice = with_prompt_injection_row(once, ran=True)
        assert len(twice) == 1

    def test_empty_manifest_gains_no_row_when_the_scan_did_not_run(self) -> None:
        """A `not_requested` row on an empty manifest would turn "coverage not
        reported" into "coverage reported, one class outstanding" — asserting
        something about classes nobody measured."""
        assert with_prompt_injection_row([], ran=False) == []

    def test_empty_manifest_does_gain_a_row_when_the_scan_ran(self) -> None:
        """A `covered` row is knowledge, not a manufactured claim."""
        rows = with_prompt_injection_row([], ran=True)
        assert _status_of(rows, PROMPT_INJECTION_CLASS) == "covered"


@pytest.mark.covers("FR-01.07")
class TestIsComplete:
    def test_empty_manifest_is_not_complete(self) -> None:
        """An absent manifest means "we do not know what was covered" — it must
        never read as a clean sweep."""
        assert is_complete([]) is False

    def test_degraded_class_is_not_complete(self) -> None:
        coverage = build_coverage(
            available={"sast", "sca", "secrets"},
            scan_errors=[{"scanner": "trivy", "reason": "timeout", "detail": ""}],
        )
        assert is_complete(coverage) is False


@pytest.mark.covers("FR-01.07")
class TestFindingClass:
    @pytest.mark.parametrize(
        "finding,expected",
        [
            ({"type": "sast", "source": "semgrep"}, "sast"),
            ({"type": "sca", "source": "trivy"}, "sca"),
            ({"type": "secret_detection", "source": "gitleaks"}, "secrets"),
            ({"type": "secrets", "source": "gitleaks"}, "secrets"),
            ({"type": "prompt_injection", "source": "shipwright"}, "prompt_injection"),
            ({"source": "semgrep"}, "sast"),
            ({"source": "trivy"}, "sca"),
            ({"source": "gitleaks"}, "secrets"),
        ],
    )
    def test_maps_to_a_coverage_class(self, finding: dict, expected: str) -> None:
        assert finding_class(finding) == expected

    def test_unknown_finding_has_no_class(self) -> None:
        assert finding_class({"type": "?", "source": "?"}) is None

    def test_non_dict_is_tolerated(self) -> None:
        assert finding_class("not-a-dict") is None  # type: ignore[arg-type]

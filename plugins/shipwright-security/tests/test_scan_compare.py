"""Tests for the coverage-gated run-to-run comparison (``scan_compare``).

AC-5 of iterate-2026-07-27-security-coverage-manifest: a finding present on
Monday and gone on Tuesday means FIXED only if Tuesday checked the same class.
Where the later scan did not cover the class, the comparison says so instead of
reporting the finding as gone. Nothing per-finding is stored — the answer is
derived from the two sidecars on demand.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from scan_compare import compare_scans, fingerprint  # noqa: E402
from scan_coverage import build_coverage  # noqa: E402


def _finding(
    *, source: str = "semgrep", rule: str = "r1", file: str = "a.py",
    line: int = 1, severity: str = "high", type_: str = "sast",
) -> dict:
    return {
        "source": source, "rule": rule, "affected_file": file,
        "affected_line": line, "severity": severity, "type": type_,
    }


def _sidecar(findings: list[dict], available: set[str]) -> dict:
    return {"findings": findings, "coverage": build_coverage(available=available)}


_SECRET = {"source": "gitleaks", "rule": "aws-key", "affected_file": "s.py",
           "affected_line": 3, "severity": "critical", "type": "secret_detection"}


@pytest.mark.covers("FR-01.07")
class TestFingerprint:
    def test_is_stable_across_runs(self) -> None:
        assert fingerprint(_finding()) == fingerprint(_finding())

    def test_distinguishes_line_numbers(self) -> None:
        assert fingerprint(_finding(line=1)) != fingerprint(_finding(line=2))

    def test_tolerates_missing_fields(self) -> None:
        assert isinstance(fingerprint({}), str)


@pytest.mark.covers("FR-01.07")
class TestComparableGround:
    def test_class_covered_by_both_is_comparable(self) -> None:
        prev = _sidecar([_finding()], {"sast"})
        curr = _sidecar([], {"sast"})
        result = compare_scans(prev, curr)
        assert result["comparable"] == ["sast"]
        assert result["counts"]["resolved"] == 1

    def test_class_not_covered_by_the_later_scan_is_not_resolved(self) -> None:
        """The whole point: gitleaks was uninstalled between runs, so the
        secret finding vanished from the output. It is NOT fixed."""
        prev = _sidecar([_SECRET], {"sast", "secrets"})
        curr = _sidecar([], {"sast"})
        result = compare_scans(prev, curr)
        assert result["counts"]["resolved"] == 0
        assert "secrets" not in result["comparable"]
        reasons = {e["class"]: e["reason"] for e in result["not_comparable"]}
        assert "secrets" in reasons
        assert "later" in reasons["secrets"]

    def test_class_not_covered_by_the_earlier_scan_yields_no_new(self) -> None:
        """Symmetric: a class the earlier scan never looked at cannot make
        today's findings 'new' — they may have been there all along."""
        prev = _sidecar([], {"sast"})
        curr = _sidecar([_SECRET], {"sast", "secrets"})
        result = compare_scans(prev, curr)
        assert result["counts"]["new"] == 0
        reasons = {e["class"]: e["reason"] for e in result["not_comparable"]}
        assert "earlier" in reasons["secrets"]

    def test_class_covered_by_neither_says_so(self) -> None:
        prev = _sidecar([], {"sast"})
        curr = _sidecar([], {"sast"})
        result = compare_scans(prev, curr)
        reasons = {e["class"]: e["reason"] for e in result["not_comparable"]}
        assert "neither" in reasons["secrets"]
        assert "neither" in reasons["sca"]

    def test_missing_coverage_manifest_makes_nothing_comparable(self) -> None:
        """A sidecar written before this feature has no manifest. Fail closed:
        we cannot prove the later run covered the same ground, so nothing is
        declared resolved."""
        prev = {"findings": [_finding()]}
        curr = {"findings": []}
        result = compare_scans(prev, curr)
        assert result["comparable"] == []
        assert result["counts"]["resolved"] == 0
        assert result["coverage_known"] is False


@pytest.mark.covers("FR-01.07")
class TestBuckets:
    def test_persisting_new_and_resolved_are_partitioned(self) -> None:
        stays = _finding(rule="stays")
        goes = _finding(rule="goes")
        comes = _finding(rule="comes")
        prev = _sidecar([stays, goes], {"sast"})
        curr = _sidecar([stays, comes], {"sast"})
        result = compare_scans(prev, curr)
        assert result["counts"] == {"resolved": 1, "new": 1, "persisting": 1}
        assert result["resolved"][0]["rule"] == "goes"
        assert result["new"][0]["rule"] == "comes"

    def test_resolved_entries_carry_severity_for_rendering(self) -> None:
        prev = _sidecar([_finding(severity="critical")], {"sast"})
        curr = _sidecar([], {"sast"})
        assert compare_scans(prev, curr)["resolved"][0]["severity"] == "critical"

    def test_unclassifiable_findings_are_counted_not_resolved(self) -> None:
        odd = {"source": "?", "type": "?", "rule": "x", "severity": "low"}
        prev = _sidecar([odd], {"sast", "sca", "secrets"})
        curr = _sidecar([], {"sast", "sca", "secrets"})
        result = compare_scans(prev, curr)
        assert result["counts"]["resolved"] == 0
        assert result["unclassified"] == 1

    def test_degraded_class_is_not_comparable(self) -> None:
        """A leg that ran and produced nothing parseable covered no ground."""
        prev = _sidecar([_finding()], {"sast"})
        curr = {
            "findings": [],
            "coverage": build_coverage(
                available={"sast"},
                scan_errors=[{"scanner": "semgrep", "reason": "timeout", "detail": ""}],
            ),
        }
        result = compare_scans(prev, curr)
        assert result["counts"]["resolved"] == 0
        assert result["comparable"] == []


@pytest.mark.covers("FR-01.07")
class TestNoStoredOutcome:
    def test_comparison_does_not_mutate_its_inputs(self) -> None:
        """The reasoning that let us drop a stored per-finding outcome: the
        answer is derived, so neither sidecar is written back to."""
        prev = _sidecar([_finding()], {"sast"})
        curr = _sidecar([], {"sast"})
        import copy
        prev_before, curr_before = copy.deepcopy(prev), copy.deepcopy(curr)
        compare_scans(prev, curr)
        assert prev == prev_before
        assert curr == curr_before

    def test_result_is_json_serializable(self) -> None:
        import json
        prev = _sidecar([_finding(), _SECRET], {"sast", "secrets"})
        curr = _sidecar([_SECRET], {"sast", "secrets"})
        result = compare_scans(prev, curr)
        assert json.loads(json.dumps(result)) == result


@pytest.mark.covers("FR-01.07")
class TestMalformedInput:
    def test_non_dict_sidecars_do_not_crash(self) -> None:
        result = compare_scans(None, None)  # type: ignore[arg-type]
        assert result["counts"] == {"resolved": 0, "new": 0, "persisting": 0}

    def test_non_dict_findings_are_skipped(self) -> None:
        prev = {"findings": ["nope", _finding()], "coverage": build_coverage(available={"sast"})}
        curr = {"findings": [], "coverage": build_coverage(available={"sast"})}
        assert compare_scans(prev, curr)["counts"]["resolved"] == 1

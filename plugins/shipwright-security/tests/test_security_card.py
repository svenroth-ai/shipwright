"""Tests for the operator-facing security scan card (``security_card``).

AC-6 of iterate-2026-07-27-security-coverage-manifest: at the point of work the
operator must be told the counts per severity and asked how far to go, instead
of the tool silently deciding that the less severe findings do not matter.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from scan_coverage import build_coverage  # noqa: E402
from security_card import (  # noqa: E402
    SCAN_CARD_PREFIX,
    build_scan_action_unit,
    severity_counts,
    top_severity,
)


def _findings(**by_sev: int) -> list[dict]:
    out: list[dict] = []
    for sev, n in by_sev.items():
        out.extend(
            {"severity": sev, "source": "semgrep", "type": "sast",
             "rule": f"{sev}-{i}", "affected_file": "a.py", "affected_line": i}
            for i in range(n)
        )
    return out


_FULL_COVERAGE = build_coverage(available={"sast", "sca", "secrets"})


@pytest.mark.covers("FR-01.07")
class TestSeverityCounts:
    def test_all_five_buckets_are_present_even_at_zero(self) -> None:
        counts = severity_counts(_findings(critical=1))
        assert counts == {"critical": 1, "high": 0, "medium": 0, "low": 0, "info": 0}

    def test_unknown_severity_is_bucketed_as_medium(self) -> None:
        counts = severity_counts([{"severity": "moderate"}])
        assert counts["medium"] == 1

    def test_missing_severity_is_bucketed_as_medium(self) -> None:
        assert severity_counts([{}])["medium"] == 1

    def test_top_severity_is_the_most_severe_present(self) -> None:
        assert top_severity(severity_counts(_findings(low=5, high=1))) == "high"

    def test_top_severity_of_nothing_is_none(self) -> None:
        assert top_severity(severity_counts([])) is None


@pytest.mark.covers("FR-01.07")
class TestScanCard:
    def test_no_findings_yields_no_card(self) -> None:
        assert build_scan_action_unit(
            findings=[], coverage=_FULL_COVERAGE, repo="o/r") is None

    def test_card_states_every_severity_count(self) -> None:
        card = build_scan_action_unit(
            findings=_findings(critical=2, high=3, medium=10, low=7),
            coverage=_FULL_COVERAGE, repo="o/r",
        )
        assert card is not None
        for token in ("critical: 2", "high: 3", "medium: 10", "low: 7"):
            assert token in card["launch_payload"], token

    def test_card_asks_the_scope_question(self) -> None:
        """The tool must not decide silently how far to go."""
        card = build_scan_action_unit(
            findings=_findings(critical=2, low=20),
            coverage=_FULL_COVERAGE, repo="o/r",
        )
        payload = card["launch_payload"]
        assert "?" in payload
        assert "ask how far to go" in payload
        assert "everything (22)" in payload
        assert "critical and above (2)" in payload

    def test_title_leads_with_the_severity_split_not_a_bare_total(self) -> None:
        card = build_scan_action_unit(
            findings=_findings(critical=2, low=20),
            coverage=_FULL_COVERAGE, repo="o/r",
        )
        assert "2 critical" in card["title"]
        assert "20" in card["title"]

    def test_card_severity_is_the_most_severe_finding(self) -> None:
        card = build_scan_action_unit(
            findings=_findings(critical=1, low=9),
            coverage=_FULL_COVERAGE, repo="o/r",
        )
        assert card["severity"] == "critical"
        assert card["kind"] == "bug"

    def test_low_only_scan_is_an_improvement_not_a_bug(self) -> None:
        card = build_scan_action_unit(
            findings=_findings(low=3), coverage=_FULL_COVERAGE, repo="o/r")
        assert card["severity"] == "low"
        assert card["kind"] == "improvement"

    def test_dedup_key_is_one_card_per_repo(self) -> None:
        card = build_scan_action_unit(
            findings=_findings(high=1), coverage=_FULL_COVERAGE, repo="o/r")
        assert card["dedup_key"] == f"{SCAN_CARD_PREFIX}o/r"

    def test_card_names_what_was_not_checked(self) -> None:
        """A card that reports 3 findings from one tool must say the other
        classes were never looked at."""
        card = build_scan_action_unit(
            findings=_findings(high=3),
            coverage=build_coverage(available={"sast"}),
            repo="o/r",
        )
        assert "not checked" in card["detail"].lower()
        assert "not checked" in card["launch_payload"].lower()

    def test_card_carries_no_raw_finding_strings(self) -> None:
        """Inbox hygiene (openai-11): only aggregated counts and stable paths,
        never rule ids / descriptions / affected files."""
        findings = [{
            "severity": "high", "source": "semgrep", "type": "sast",
            "rule": "SECRET-RULE-ID", "affected_file": "very/secret/path.py",
            "description": "leaked THING", "affected_line": 4,
        }]
        card = build_scan_action_unit(
            findings=findings, coverage=_FULL_COVERAGE, repo="o/r")
        blob = card["title"] + card["detail"] + card["launch_payload"]
        for leak in ("SECRET-RULE-ID", "very/secret/path.py", "leaked THING"):
            assert leak not in blob, leak

    def test_detail_is_capped(self) -> None:
        card = build_scan_action_unit(
            findings=_findings(high=1),
            coverage=build_coverage(available=set()),
            repo="o/" + "r" * 4000,
        )
        assert len(card["detail"]) <= 1024

    def test_title_is_capped_at_160(self) -> None:
        card = build_scan_action_unit(
            findings=_findings(high=1), coverage=_FULL_COVERAGE, repo="o/" + "r" * 400)
        assert len(card["title"]) <= 160

    def test_report_path_is_included_when_given(self) -> None:
        card = build_scan_action_unit(
            findings=_findings(high=1), coverage=_FULL_COVERAGE, repo="o/r",
            report_path=".shipwright/securityreports/latest.md",
        )
        assert ".shipwright/securityreports/latest.md" in card["launch_payload"]

    def test_launch_payload_starts_with_the_slash_command(self) -> None:
        card = build_scan_action_unit(
            findings=_findings(high=1), coverage=_FULL_COVERAGE, repo="o/r")
        assert card["launch_payload"].startswith("/shipwright-security")

    def test_severity_and_kind_are_valid_triage_enums(self) -> None:
        sys.path.insert(0, str(PLUGIN_ROOT.parent.parent / "shared" / "scripts"))
        from triage import KINDS, SEVERITIES  # noqa: PLC0415
        for sev in ("critical", "high", "medium", "low", "info"):
            card = build_scan_action_unit(
                findings=_findings(**{sev: 1}), coverage=_FULL_COVERAGE, repo="o/r")
            assert card["severity"] in SEVERITIES
            assert card["kind"] in KINDS

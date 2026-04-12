"""Tests for the enhanced generate_security_report.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import generate_security_report as report_gen  # noqa: E402


# ---------------------------------------------------------------------------
# calculate_risk_level
# ---------------------------------------------------------------------------

class TestCalculateRiskLevel:

    def test_empty_returns_none(self):
        assert report_gen.calculate_risk_level([]) == "NONE"

    def test_critical_wins(self):
        findings = [
            {"severity": "critical"},
            {"severity": "low"},
        ]
        assert report_gen.calculate_risk_level(findings) == "CRITICAL"

    def test_high_without_critical(self):
        findings = [{"severity": "high"}]
        assert report_gen.calculate_risk_level(findings) == "HIGH"

    def test_five_medium_escalates_to_high(self):
        findings = [{"severity": "medium"}] * 5
        assert report_gen.calculate_risk_level(findings) == "HIGH"

    def test_one_medium_is_medium(self):
        findings = [{"severity": "medium"}]
        assert report_gen.calculate_risk_level(findings) == "MEDIUM"

    def test_only_low_is_low(self):
        findings = [{"severity": "low"}, {"severity": "info"}]
        assert report_gen.calculate_risk_level(findings) == "LOW"

    def test_new_dependency_is_medium(self):
        findings = [
            {"severity": "info", "rule": "NEW_DEPENDENCY"},
        ]
        assert report_gen.calculate_risk_level(findings) == "MEDIUM"

    def test_hooks_file_change_is_medium(self):
        findings = [
            {"severity": "low", "affected_file": "plugins/x/hooks/hooks.json"},
        ]
        assert report_gen.calculate_risk_level(findings) == "MEDIUM"


# ---------------------------------------------------------------------------
# scanner_breakdown
# ---------------------------------------------------------------------------

class TestScannerBreakdown:

    def test_empty(self):
        assert report_gen.scanner_breakdown([]) == {}

    def test_grouping(self):
        findings = [
            {"source": "semgrep", "severity": "high"},
            {"source": "semgrep", "severity": "low"},
            {"source": "trivy", "severity": "critical"},
        ]
        breakdown = report_gen.scanner_breakdown(findings)
        assert breakdown["semgrep"]["total"] == 2
        assert breakdown["semgrep"]["high"] == 1
        assert breakdown["semgrep"]["low"] == 1
        assert breakdown["trivy"]["total"] == 1
        assert breakdown["trivy"]["critical"] == 1


# ---------------------------------------------------------------------------
# load_findings_from_file
# ---------------------------------------------------------------------------

class TestLoadFindingsFromFile:

    def test_nonexistent_returns_empty(self, tmp_path):
        assert report_gen.load_findings_from_file(tmp_path / "nope.json") == []

    def test_loads_findings_key(self, tmp_path):
        p = tmp_path / "f.json"
        p.write_text(json.dumps({"findings": [{"id": "a"}, {"id": "b"}]}))
        result = report_gen.load_findings_from_file(p)
        assert len(result) == 2

    def test_loads_data_key_fallback(self, tmp_path):
        p = tmp_path / "f.json"
        p.write_text(json.dumps({"data": [{"id": "x"}]}))
        result = report_gen.load_findings_from_file(p)
        assert len(result) == 1

    def test_invalid_json_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not-json")
        assert report_gen.load_findings_from_file(p) == []


# ---------------------------------------------------------------------------
# generate_standard_report
# ---------------------------------------------------------------------------

class TestStandardReport:

    def test_empty_report(self):
        report = report_gen.generate_standard_report([], repo_name="test")
        assert "# Security Report: test" in report
        assert "Risk Level" in report
        assert "NONE" in report

    def test_report_has_severity_table(self):
        findings = [
            {"severity": "critical", "type": "sca", "rule": "CVE-1"},
            {"severity": "high", "type": "sast", "rule": "R1"},
        ]
        report = report_gen.generate_standard_report(findings)
        assert "Critical" in report
        assert "High" in report
        assert "## Findings" in report


# ---------------------------------------------------------------------------
# generate_pr_report
# ---------------------------------------------------------------------------

class TestPRReport:

    def test_empty_pr_report_is_clean(self):
        report = report_gen.generate_pr_report([])
        assert report_gen.PR_COMMENT_MARKER in report
        assert "NONE" in report
        assert "No security findings" in report

    def test_pr_report_has_critical_warning(self):
        findings = [
            {"severity": "critical", "source": "trivy", "rule": "CVE-1",
             "affected_file": "package.json", "description": "Bad"},
        ]
        report = report_gen.generate_pr_report(findings)
        assert "CRITICAL" in report
        assert "should not be merged" in report

    def test_pr_report_has_scanner_breakdown_table(self):
        findings = [
            {"severity": "high", "source": "semgrep", "rule": "R1",
             "affected_file": "a.py", "description": "desc"},
            {"severity": "medium", "source": "trivy", "rule": "CVE-1",
             "affected_file": "p.json", "description": "desc"},
        ]
        report = report_gen.generate_pr_report(findings)
        assert "| Scanner " in report
        assert "semgrep" in report
        assert "trivy" in report

    def test_pr_report_has_marker_for_comment_update(self):
        report = report_gen.generate_pr_report([])
        assert report_gen.PR_COMMENT_MARKER in report

    def test_pr_report_sorts_by_severity(self):
        findings = [
            {"severity": "low", "source": "s", "rule": "low-rule",
             "affected_file": "a", "description": ""},
            {"severity": "critical", "source": "s", "rule": "crit-rule",
             "affected_file": "a", "description": ""},
        ]
        report = report_gen.generate_pr_report(findings)
        # Critical should appear before low in the findings table
        crit_idx = report.find("crit-rule")
        low_idx = report.find("low-rule")
        assert crit_idx < low_idx
        assert crit_idx > 0

    def test_pr_report_truncates_at_15(self):
        findings = [
            {"severity": "medium", "source": "s", "rule": f"R{i}",
             "affected_file": "f", "description": "d"}
            for i in range(20)
        ]
        report = report_gen.generate_pr_report(findings)
        assert "more findings" in report


# ---------------------------------------------------------------------------
# main() CLI
# ---------------------------------------------------------------------------

class TestMainCLI:

    def test_reads_input_file(self, tmp_path):
        findings_file = tmp_path / "findings.json"
        findings_file.write_text(json.dumps({
            "findings": [
                {"severity": "high", "source": "semgrep", "rule": "R1",
                 "affected_file": "a.py", "description": "test"}
            ]
        }))
        output_file = tmp_path / "report.md"
        argv = [
            "generate_security_report.py",
            "--input", str(findings_file),
            "--output", str(output_file),
            "--pr-mode",
        ]
        with patch.object(sys, "argv", argv):
            rc = report_gen.main()
        assert rc == 0
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "HIGH" in content

    def test_merges_prompt_risks(self, tmp_path):
        findings_file = tmp_path / "findings.json"
        findings_file.write_text(json.dumps({
            "findings": [
                {"severity": "low", "source": "semgrep", "rule": "R1",
                 "affected_file": "a.py", "description": "test"}
            ]
        }))
        prompt_file = tmp_path / "prompt.json"
        prompt_file.write_text(json.dumps({
            "findings": [
                {"severity": "critical", "source": "shipwright-prompt-scan",
                 "rule": "HOOKS_EXTERNAL_DOWNLOAD",
                 "affected_file": "hooks.json", "description": "curl pipe"}
            ]
        }))
        output_file = tmp_path / "report.md"
        argv = [
            "generate_security_report.py",
            "--input", str(findings_file),
            "--prompt-risks", str(prompt_file),
            "--output", str(output_file),
            "--pr-mode",
        ]
        with patch.object(sys, "argv", argv):
            rc = report_gen.main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "CRITICAL" in content
        assert "shipwright-prompt-scan" in content

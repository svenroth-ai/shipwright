"""Tests for finding classification and report generation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from lib.aikido_client import classify_finding  # noqa: E402


class TestClassificationCoverage:
    """Test that all Aikido finding types are classified correctly."""

    @pytest.mark.parametrize("finding_type,expected", [
        ("sca", "auto-fixable"),
        ("dependency", "auto-fixable"),
        ("sast", "agent-fixable"),
        ("secret_detection", "agent-fixable"),
        ("iac", "needs-review"),
        ("container", "needs-review"),
        ("unknown", "needs-review"),
    ])
    def test_type_classification_high_severity(self, finding_type, expected):
        finding = {"severity": "high", "type": finding_type}
        assert classify_finding(finding) == expected

    @pytest.mark.parametrize("severity,expected", [
        ("critical", False),
        ("high", False),
        ("medium", False),
        ("low", True),
        ("info", True),
        ("informational", True),
    ])
    def test_low_severity_always_informational(self, severity, expected):
        finding = {"severity": severity, "type": "sast"}
        result = classify_finding(finding)
        assert (result == "informational") == expected

    def test_full_sample_classification(self, sample_aikido_response):
        """Classify all findings from sample response."""
        expected = {
            "aikido-001": "auto-fixable",      # critical + sca
            "aikido-002": "agent-fixable",      # high + sast
            "aikido-003": "agent-fixable",      # medium + sast
            "aikido-004": "informational",      # low + sast
            "aikido-005": "agent-fixable",      # high + secret_detection
        }

        for finding in sample_aikido_response:
            fid = finding["id"]
            result = classify_finding(finding)
            assert result == expected[fid], f"{fid}: expected {expected[fid]}, got {result}"


class TestReportGeneration:
    """Test report generation from findings."""

    def test_import_generate_report(self):
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))
        import importlib
        if "generate_security_report" in sys.modules:
            importlib.reload(sys.modules["generate_security_report"])
        else:
            import generate_security_report  # noqa: F401
        from generate_security_report import generate_report

        report = generate_report([], repo_name="test/repo")
        assert "# Security Report: test/repo" in report
        assert "**Total Findings:** 0" in report

    def test_report_with_findings(self, sample_aikido_response):
        sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))
        from generate_security_report import generate_report

        report = generate_report(sample_aikido_response, repo_name="svenroth-ai/claude-skills")
        assert "**Total Findings:** 5" in report
        assert "Critical" in report
        assert "svenroth-ai/claude-skills" in report

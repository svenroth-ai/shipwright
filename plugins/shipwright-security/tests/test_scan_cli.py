"""Tests for scripts/tools/scan.py CLI wrapper."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import scan  # noqa: E402


# ---------------------------------------------------------------------------
# parse_scan_types
# ---------------------------------------------------------------------------

class TestParseScanTypes:

    def test_none_returns_none(self):
        assert scan.parse_scan_types(None) is None

    def test_empty_returns_none(self):
        assert scan.parse_scan_types("") is None

    def test_single_type(self):
        assert scan.parse_scan_types("sast") == ["sast"]

    def test_multiple_types(self):
        result = scan.parse_scan_types("sast,sca,secret-detection")
        assert result == ["sast", "sca", "secrets"]

    def test_alias_secret_detection(self):
        assert scan.parse_scan_types("secret-detection") == ["secrets"]

    def test_alias_secret_underscore(self):
        assert scan.parse_scan_types("secret_detection") == ["secrets"]

    def test_raw_secrets(self):
        assert scan.parse_scan_types("secrets") == ["secrets"]

    def test_whitespace_tolerance(self):
        assert scan.parse_scan_types(" sast , sca ") == ["sast", "sca"]

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown scan type"):
            scan.parse_scan_types("xss")


# ---------------------------------------------------------------------------
# parse_fail_on
# ---------------------------------------------------------------------------

class TestParseFailOn:

    def test_none_returns_empty(self):
        assert scan.parse_fail_on(None) == set()

    def test_empty_returns_empty(self):
        assert scan.parse_fail_on("") == set()

    def test_single(self):
        assert scan.parse_fail_on("critical") == {"critical"}

    def test_multiple(self):
        assert scan.parse_fail_on("critical,high") == {"critical", "high"}

    def test_unknown_severity_raises(self):
        with pytest.raises(ValueError, match="Unknown severity"):
            scan.parse_fail_on("catastrophic")


# ---------------------------------------------------------------------------
# build_config
# ---------------------------------------------------------------------------

class TestBuildConfig:

    def test_empty_findings(self):
        config = scan.build_config([], repo="test", scanner="oss")
        assert config["repo"] == "test"
        assert config["scanner"] == "oss"
        assert config["total_findings"] == 0
        assert config["findings"] == []
        assert config["by_severity"] == {
            "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0
        }
        assert config["remediation"]["open"] == 0

    def test_severity_counting(self):
        findings = [
            {"severity": "critical", "id": "f1"},
            {"severity": "high", "id": "f2"},
            {"severity": "high", "id": "f3"},
            {"severity": "low", "id": "f4"},
        ]
        config = scan.build_config(findings, repo="test", scanner="oss")
        assert config["total_findings"] == 4
        assert config["by_severity"]["critical"] == 1
        assert config["by_severity"]["high"] == 2
        assert config["by_severity"]["low"] == 1
        assert config["remediation"]["open"] == 4

    def test_has_iso_scan_date(self):
        config = scan.build_config([], repo="test", scanner="oss")
        assert "scan_date" in config
        # ISO format check (basic)
        assert "T" in config["scan_date"]


# ---------------------------------------------------------------------------
# count_above_threshold
# ---------------------------------------------------------------------------

class TestCountAboveThreshold:

    def test_empty_fail_on_returns_zero(self):
        findings = [{"severity": "critical"}, {"severity": "high"}]
        assert scan.count_above_threshold(findings, set()) == 0

    def test_counts_matching_severities(self):
        findings = [
            {"severity": "critical"},
            {"severity": "high"},
            {"severity": "medium"},
            {"severity": "low"},
        ]
        assert scan.count_above_threshold(findings, {"critical", "high"}) == 2

    def test_case_insensitive(self):
        findings = [{"severity": "CRITICAL"}, {"severity": "High"}]
        assert scan.count_above_threshold(findings, {"critical", "high"}) == 2

    def test_no_matches(self):
        findings = [{"severity": "low"}, {"severity": "info"}]
        assert scan.count_above_threshold(findings, {"critical"}) == 0


# ---------------------------------------------------------------------------
# main() end-to-end with mocked backend
# ---------------------------------------------------------------------------

class TestMainE2E:

    def test_writes_output_file(self, tmp_path):
        findings = [
            {"id": "f1", "severity": "medium", "type": "sast", "rule": "test", "source": "semgrep"},
        ]

        class FakeBackend:
            capabilities = {"sast"}

            def scan(self, target, scan_types=None):
                return findings

        output_file = tmp_path / "findings.json"
        argv = [
            "scan.py",
            "--path", str(tmp_path),
            "--output", str(output_file),
            "--backend", "oss",
        ]

        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", return_value=FakeBackend(), create=True):
            rc = scan.main()

        assert rc == 0
        assert output_file.exists()
        config = json.loads(output_file.read_text(encoding="utf-8"))
        assert config["total_findings"] == 1
        assert config["findings"][0]["id"] == "f1"

    def test_fail_on_critical_returns_1(self, tmp_path):
        findings = [
            {"id": "f1", "severity": "critical", "type": "sca", "rule": "CVE-1", "source": "trivy"},
        ]

        class FakeBackend:
            capabilities = {"sca"}

            def scan(self, target, scan_types=None):
                return findings

        argv = [
            "scan.py",
            "--path", str(tmp_path),
            "--output", str(tmp_path / "out.json"),
            "--fail-on", "critical,high",
        ]

        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", return_value=FakeBackend(), create=True):
            rc = scan.main()

        assert rc == 1

    def test_missing_path_returns_2(self, tmp_path):
        argv = [
            "scan.py",
            "--path", str(tmp_path / "does-not-exist"),
        ]
        with patch.object(sys, "argv", argv):
            rc = scan.main()
        assert rc == 2

    def test_backend_not_configured_returns_2(self, tmp_path):
        def raise_rt(_name):
            raise RuntimeError("No backend available")

        argv = ["scan.py", "--path", str(tmp_path)]
        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", side_effect=raise_rt, create=True):
            rc = scan.main()
        assert rc == 2

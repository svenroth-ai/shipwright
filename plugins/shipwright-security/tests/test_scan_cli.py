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


# ---------------------------------------------------------------------------
# --sarif-dir + --input-from-cache (Iterate 2: sec-ci-activation)
# ---------------------------------------------------------------------------

class TestSarifDir:

    def test_writes_default_sarif_files_on_clean_scan(self, tmp_path):
        class FakeBackend:
            capabilities = {"sast", "sca", "secrets"}

            def scan(self, target, scan_types=None):
                return []

        sarif_dir = tmp_path / "sarif"
        argv = [
            "scan.py",
            "--path", str(tmp_path),
            "--sarif-dir", str(sarif_dir),
        ]

        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", return_value=FakeBackend(), create=True):
            rc = scan.main()

        assert rc == 0
        # All three default scanner sources must have a SARIF file even on empty scans
        for source in ("semgrep", "trivy", "gitleaks"):
            sarif_file = sarif_dir / f"{source}.sarif"
            assert sarif_file.exists(), f"missing SARIF file for {source}"
            doc = json.loads(sarif_file.read_text(encoding="utf-8"))
            assert doc["version"] == "2.1.0"
            assert doc["runs"][0]["tool"]["driver"]["name"] == source
            assert doc["runs"][0]["results"] == []

    def test_groups_findings_by_source(self, tmp_path):
        findings = [
            {"id": "s1", "severity": "high", "type": "sast", "rule": "r1", "source": "semgrep",
             "affected_file": "a.py", "affected_line": 1, "description": "d"},
            {"id": "t1", "severity": "critical", "type": "sca", "rule": "CVE-1", "source": "trivy",
             "affected_file": "req.txt", "description": "d"},
            {"id": "s2", "severity": "medium", "type": "sast", "rule": "r2", "source": "semgrep",
             "affected_file": "b.py", "affected_line": 2, "description": "d"},
        ]

        class FakeBackend:
            capabilities = {"sast", "sca"}

            def scan(self, target, scan_types=None):
                return findings

        sarif_dir = tmp_path / "sarif"
        argv = [
            "scan.py",
            "--path", str(tmp_path),
            "--sarif-dir", str(sarif_dir),
        ]
        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", return_value=FakeBackend(), create=True):
            rc = scan.main()

        assert rc == 0
        semgrep_doc = json.loads((sarif_dir / "semgrep.sarif").read_text(encoding="utf-8"))
        trivy_doc = json.loads((sarif_dir / "trivy.sarif").read_text(encoding="utf-8"))
        gitleaks_doc = json.loads((sarif_dir / "gitleaks.sarif").read_text(encoding="utf-8"))
        assert len(semgrep_doc["runs"][0]["results"]) == 2
        assert len(trivy_doc["runs"][0]["results"]) == 1
        assert gitleaks_doc["runs"][0]["results"] == []  # placeholder still emitted


class TestInputFromCache:

    def test_skips_scanner_when_cache_exists(self, tmp_path):
        cache = tmp_path / "findings.json"
        cache.write_text(
            json.dumps({
                "scanner": "oss",
                "findings": [
                    {"id": "f1", "severity": "high", "type": "sast", "rule": "r1",
                     "source": "semgrep", "affected_file": "a.py", "affected_line": 1,
                     "description": "d"},
                ],
            }),
            encoding="utf-8",
        )

        argv = [
            "scan.py",
            "--path", str(tmp_path),
            "--input-from-cache", str(cache),
            "--output", str(tmp_path / "out.json"),
        ]

        # If get_backend is invoked at all the test fails — cache must short-circuit
        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", side_effect=AssertionError("must not invoke backend"),
                   create=True):
            rc = scan.main()

        assert rc == 0
        out = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
        assert out["total_findings"] == 1
        assert out["findings"][0]["id"] == "f1"

    def test_falls_back_to_scan_when_cache_missing(self, tmp_path):
        # cache path provided but file does NOT exist → scanner runs normally
        class FakeBackend:
            capabilities = {"sast"}

            def scan(self, target, scan_types=None):
                return [{"id": "live", "severity": "low", "type": "sast", "rule": "r",
                         "source": "semgrep", "affected_file": "x.py", "affected_line": 1,
                         "description": "d"}]

        argv = [
            "scan.py",
            "--path", str(tmp_path),
            "--input-from-cache", str(tmp_path / "missing.json"),
            "--output", str(tmp_path / "out.json"),
        ]
        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", return_value=FakeBackend(), create=True):
            rc = scan.main()
        assert rc == 0
        out = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
        assert out["findings"][0]["id"] == "live"

    def test_combined_cache_plus_sarif(self, tmp_path):
        # CI's expected pattern: read findings.json from disk, write SARIF, no scan.
        cache = tmp_path / "findings.json"
        cache.write_text(
            json.dumps({
                "scanner": "oss",
                "findings": [
                    {"id": "f1", "severity": "critical", "type": "sca", "rule": "CVE-1",
                     "source": "trivy", "affected_file": "r.txt", "description": "d"},
                ],
            }),
            encoding="utf-8",
        )

        sarif_dir = tmp_path / "sarif"
        argv = [
            "scan.py",
            "--path", str(tmp_path),
            "--input-from-cache", str(cache),
            "--sarif-dir", str(sarif_dir),
        ]
        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", side_effect=AssertionError("must not scan"),
                   create=True):
            rc = scan.main()

        assert rc == 0
        trivy_doc = json.loads((sarif_dir / "trivy.sarif").read_text(encoding="utf-8"))
        assert len(trivy_doc["runs"][0]["results"]) == 1
        # placeholders still emitted for the other scanners
        assert (sarif_dir / "semgrep.sarif").exists()
        assert (sarif_dir / "gitleaks.sarif").exists()

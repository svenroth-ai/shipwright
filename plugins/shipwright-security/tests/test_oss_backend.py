"""Tests for OSS scanner backend."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/lib is on path
PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from oss_backend import OSSBackend, _run_semgrep, _run_trivy, _run_gitleaks

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# OSSBackend
# ---------------------------------------------------------------------------

class TestOSSBackend:

    def test_name(self):
        backend = OSSBackend()
        assert backend.name == "oss"
        assert backend.requires_cloud is False

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/" + t if t in ("semgrep", "trivy") else None)
    def test_capabilities_partial(self, mock_which):
        backend = OSSBackend()
        assert backend.capabilities == {"sast", "sca"}

    @patch("shutil.which", return_value=None)
    def test_not_configured_when_nothing_installed(self, mock_which):
        backend = OSSBackend()
        assert backend.is_configured() is False

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/gitleaks" if t == "gitleaks" else None)
    def test_configured_with_single_tool(self, mock_which):
        backend = OSSBackend()
        assert backend.is_configured() is True
        assert backend.capabilities == {"secrets"}

    def test_setup_instructions_contains_tools(self):
        backend = OSSBackend()
        instructions = backend.get_setup_instructions()
        assert "semgrep" in instructions
        assert "trivy" in instructions
        assert "gitleaks" in instructions


# ---------------------------------------------------------------------------
# Tool runners (mocked subprocess)
# ---------------------------------------------------------------------------

class TestRunSemgrep:

    def test_parses_output(self):
        fixture = json.loads((FIXTURES_DIR / "sample_semgrep_output.json").read_text())
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(fixture)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            findings = _run_semgrep("/tmp/test")

        assert len(findings) == 3
        assert findings[0]["source"] == "semgrep"
        assert findings[0]["type"] == "sast"


class TestRunTrivy:

    def test_parses_output(self):
        fixture = json.loads((FIXTURES_DIR / "sample_trivy_output.json").read_text())
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(fixture)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            findings = _run_trivy("/tmp/test")

        assert len(findings) == 3
        assert findings[0]["source"] == "trivy"
        assert findings[0]["type"] == "sca"
        assert findings[0]["cve_id"] == "CVE-2024-1234"


class TestRunGitleaks:

    def test_parses_output(self):
        fixture = json.loads((FIXTURES_DIR / "sample_gitleaks_output.json").read_text())
        mock_result = MagicMock()
        mock_result.returncode = 1  # gitleaks returns 1 when findings exist
        mock_result.stdout = json.dumps(fixture)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            findings = _run_gitleaks("/tmp/test")

        assert len(findings) == 2
        assert findings[0]["source"] == "gitleaks"
        assert findings[0]["type"] == "secret_detection"

    def test_returns_empty_on_timeout(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gitleaks", timeout=300)):
            findings = _run_gitleaks("/tmp/test")
        assert findings == []

    def test_returns_empty_on_missing_binary(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            findings = _run_gitleaks("/tmp/test")
        assert findings == []


# ---------------------------------------------------------------------------
# Full scan (mocked)
# ---------------------------------------------------------------------------

class TestOSSBackendScan:

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/" + t)
    def test_full_scan_combines_all_tools(self, mock_which):
        semgrep_fixture = json.loads((FIXTURES_DIR / "sample_semgrep_output.json").read_text())
        trivy_fixture = json.loads((FIXTURES_DIR / "sample_trivy_output.json").read_text())
        gitleaks_fixture = json.loads((FIXTURES_DIR / "sample_gitleaks_output.json").read_text())

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.stderr = ""
            if "semgrep" in cmd[0]:
                result.returncode = 0
                result.stdout = json.dumps(semgrep_fixture)
            elif "trivy" in cmd[0]:
                result.returncode = 0
                result.stdout = json.dumps(trivy_fixture)
            elif "gitleaks" in cmd[0]:
                result.returncode = 1
                result.stdout = json.dumps(gitleaks_fixture)
            return result

        with patch("subprocess.run", side_effect=mock_run):
            backend = OSSBackend()
            findings = backend.scan("/tmp/test")

        assert len(findings) == 8  # 3 semgrep + 3 trivy + 2 gitleaks
        # All findings should have _remediation_class
        for f in findings:
            assert "_remediation_class" in f

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/semgrep" if t == "semgrep" else None)
    def test_scan_only_available_tools(self, mock_which):
        semgrep_fixture = json.loads((FIXTURES_DIR / "sample_semgrep_output.json").read_text())
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(semgrep_fixture)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            backend = OSSBackend()
            findings = backend.scan("/tmp/test")

        assert len(findings) == 3
        assert all(f["source"] == "semgrep" for f in findings)

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/" + t)
    def test_scan_with_type_filter(self, mock_which):
        trivy_fixture = json.loads((FIXTURES_DIR / "sample_trivy_output.json").read_text())
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(trivy_fixture)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            backend = OSSBackend()
            findings = backend.scan("/tmp/test", scan_types=["sca"])

        assert len(findings) == 3
        assert all(f["source"] == "trivy" for f in findings)

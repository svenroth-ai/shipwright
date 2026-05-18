"""Tests for scanner backend abstraction and registry."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure scripts/lib is on path
PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from scanner_backend import (
    BACKEND_REGISTRY,
    ScannerBackend,
    check_security_available,
    classify_finding,
    get_backend,
    register_backend,
)


# ---------------------------------------------------------------------------
# classify_finding (backend-agnostic)
# ---------------------------------------------------------------------------

class TestClassifyFinding:

    def test_low_severity_is_informational(self):
        assert classify_finding({"severity": "low", "type": "sast"}) == "informational"

    def test_info_severity_is_informational(self):
        assert classify_finding({"severity": "info", "type": "sca"}) == "informational"

    def test_sca_is_auto_fixable(self):
        assert classify_finding({"severity": "high", "type": "sca"}) == "auto-fixable"

    def test_dependency_is_auto_fixable(self):
        assert classify_finding({"severity": "critical", "type": "dependency"}) == "auto-fixable"

    def test_sast_is_agent_fixable(self):
        assert classify_finding({"severity": "high", "type": "sast"}) == "agent-fixable"

    def test_secret_detection_is_agent_fixable(self):
        assert classify_finding({"severity": "high", "type": "secret_detection"}) == "agent-fixable"

    def test_unknown_type_needs_review(self):
        assert classify_finding({"severity": "high", "type": "iac"}) == "needs-review"

    def test_empty_finding(self):
        # Empty severity is "" which is not in ("low", "info", "informational"),
        # and empty type is not in any fixable set → needs-review
        assert classify_finding({}) == "needs-review"


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------

class TestBackendRegistry:

    def test_register_backend_decorator(self):
        # Create a dummy backend
        @register_backend
        class DummyBackend(ScannerBackend):
            name = "_test_dummy"
            capabilities = {"test"}
            requires_cloud = False

            def is_configured(self): return True
            def scan(self, target, scan_types=None): return []
            def get_setup_instructions(self): return "Install test"

        assert "_test_dummy" in BACKEND_REGISTRY
        assert BACKEND_REGISTRY["_test_dummy"] is DummyBackend

        # Cleanup
        del BACKEND_REGISTRY["_test_dummy"]


# ---------------------------------------------------------------------------
# check_security_available
# ---------------------------------------------------------------------------

class TestCheckSecurityAvailable:

    @patch.dict("os.environ", {"AIKIDO_CLIENT_ID": "test"}, clear=False)
    def test_aikido_credentials_available(self):
        assert check_security_available() is True

    @patch.dict("os.environ", {"SHIPWRIGHT_SCANNER_BACKEND": "oss"}, clear=False)
    def test_explicit_backend_env(self):
        assert check_security_available() is True

    @patch.dict("os.environ", {}, clear=True)
    @patch("shutil.which", return_value=None)
    def test_nothing_available(self, mock_which):
        assert check_security_available() is False

    @patch.dict("os.environ", {}, clear=True)
    @patch("shutil.which", side_effect=lambda t: "/usr/bin/semgrep" if t == "semgrep" else None)
    def test_semgrep_on_path(self, mock_which):
        assert check_security_available() is True


# ---------------------------------------------------------------------------
# get_backend
# ---------------------------------------------------------------------------

class TestGetBackend:

    @patch.dict("os.environ", {}, clear=True)
    @patch("shutil.which", return_value=None)
    def test_explicit_name_not_in_registry(self, mock_which):
        # Isolate the environment so an explicit name that is not in the
        # registry deterministically falls through to the "No security
        # scanner backend" error. Without this the test is non-hermetic: a
        # host with semgrep/trivy/gitleaks installed (CI runner after the
        # scanner-install step, or a dev box) auto-detects the OSS backend
        # and get_backend() returns it instead of raising. Mirrors the
        # isolation of test_no_backend_raises below.
        saved = dict(BACKEND_REGISTRY)
        BACKEND_REGISTRY.clear()
        try:
            with pytest.raises(RuntimeError, match="No security scanner backend"):
                get_backend("nonexistent_backend_xyz")
        finally:
            BACKEND_REGISTRY.update(saved)

    @patch.dict("os.environ", {}, clear=True)
    @patch("shutil.which", return_value=None)
    def test_no_backend_raises(self, mock_which):
        # Temporarily remove all backends to test the error path
        saved = dict(BACKEND_REGISTRY)
        BACKEND_REGISTRY.clear()
        try:
            with pytest.raises(RuntimeError, match="No security scanner backend"):
                get_backend()
        finally:
            BACKEND_REGISTRY.update(saved)

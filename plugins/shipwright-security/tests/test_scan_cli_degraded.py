"""scan.py — degraded-scan propagation, exit codes, cache round-trip.

(iterate-2026-06-05-scanner-degraded-marker)

A degraded scanner leg (recorded on OSSBackend.scan_errors) must reach the
threshold layer: build_config writes findings.json `degraded`/`scan_errors`,
and scan.main() returns exit 2 (scan error) BEFORE the --fail-on threshold so a
fataled scan never reports as a clean exit 0. The cache (--input-from-cache)
round-trips the markers so the SARIF re-read stays fail-closed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import scan  # noqa: E402


class TestBuildConfigDegraded:

    def test_clean_scan_is_not_degraded(self):
        config = scan.build_config([], repo="r", scanner="oss")
        assert config["degraded"] is False
        assert config["scan_errors"] == []

    def test_scan_errors_set_marks_degraded(self):
        errs = [{"scanner": "gitleaks", "reason": "empty_output", "detail": "FTL"}]
        config = scan.build_config([], repo="r", scanner="oss", scan_errors=errs)
        assert config["degraded"] is True
        assert config["scan_errors"] == errs

    def test_degraded_independent_of_findings(self):
        """A degraded leg with 0 surviving findings still flags degraded — the
        whole point (clean-0 vs degraded-0 must differ)."""
        errs = [{"scanner": "semgrep", "reason": "timeout", "detail": "..."}]
        config = scan.build_config([], repo="r", scanner="oss", scan_errors=errs)
        assert config["total_findings"] == 0
        assert config["degraded"] is True


class _DegradedBackend:
    capabilities = {"sast", "secrets"}
    scan_errors = [
        {"scanner": "gitleaks", "reason": "empty_output", "detail": "FTL fatal"}
    ]

    def scan(self, target, scan_types=None):
        return []  # secrets leg degraded → 0 findings, but NOT clean


class TestDegradedScanCLI:

    def test_degraded_returns_2_and_writes_marker(self, tmp_path):
        out = tmp_path / "findings.json"
        argv = ["scan.py", "--path", str(tmp_path), "--output", str(out)]
        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", return_value=_DegradedBackend(), create=True):
            rc = scan.main()
        assert rc == 2  # scan error, not a clean 0
        config = json.loads(out.read_text(encoding="utf-8"))
        assert config["degraded"] is True
        assert config["scan_errors"][0]["scanner"] == "gitleaks"

    def test_degraded_beats_clean_threshold(self, tmp_path):
        """Even with no --fail-on (threshold passes), degraded → exit 2."""
        argv = ["scan.py", "--path", str(tmp_path)]
        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", return_value=_DegradedBackend(), create=True):
            rc = scan.main()
        assert rc == 2

    def test_clean_scan_still_returns_0(self, tmp_path):
        class CleanBackend:
            capabilities = {"sast"}
            scan_errors: list = []

            def scan(self, target, scan_types=None):
                return []

        argv = ["scan.py", "--path", str(tmp_path)]
        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", return_value=CleanBackend(), create=True):
            rc = scan.main()
        assert rc == 0

    def test_backend_without_scan_errors_attr_is_not_degraded(self, tmp_path):
        """Aikido / mocks that never set scan_errors default to not-degraded."""
        class NoAttrBackend:
            capabilities = {"sast"}

            def scan(self, target, scan_types=None):
                return []

        out = tmp_path / "f.json"
        argv = ["scan.py", "--path", str(tmp_path), "--output", str(out)]
        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend", return_value=NoAttrBackend(), create=True):
            rc = scan.main()
        assert rc == 0
        assert json.loads(out.read_text(encoding="utf-8"))["degraded"] is False

    def test_cache_roundtrips_degraded(self, tmp_path):
        """A cached findings.json carrying degraded must keep degraded on the
        --input-from-cache (SARIF) re-read — exit 2, marker re-emitted."""
        cache = tmp_path / "findings.json"
        cache.write_text(json.dumps({
            "scanner": "oss",
            "findings": [],
            "degraded": True,
            "scan_errors": [
                {"scanner": "trivy", "reason": "nonzero_exit", "detail": "boom"}
            ],
        }), encoding="utf-8")
        out = tmp_path / "out.json"
        argv = [
            "scan.py", "--path", str(tmp_path),
            "--input-from-cache", str(cache), "--output", str(out),
        ]
        with patch.object(sys, "argv", argv), \
             patch("scan.get_backend",
                   side_effect=AssertionError("must not invoke backend"), create=True):
            rc = scan.main()
        assert rc == 2
        config = json.loads(out.read_text(encoding="utf-8"))
        assert config["degraded"] is True
        assert config["scan_errors"][0]["scanner"] == "trivy"

"""Degraded-scan surfacing across the report + CI-gate layers.

Follow-up to iterate-2026-06-05-gitleaks-report-path: a scanner that fataled or
produced a truncated report must not pass as a clean (green) leg. The source
channel (`oss_backend.scan_errors`) is tested in test_oss_backend.py; the
`scan.py` config/exit contract in test_scan_cli.py. This module covers the two
remaining consumers:

  - generate_security_report.py — the CI combined report renders a degraded
    banner (so the PR comment can't say "✅ No findings" while the gate blocks).
  - run_scan_and_report.py — the local report embeds degraded + exits non-zero.
  - .github/workflows/security.yml — the critical-gate fails closed on
    `findings.json.degraded` (a static workflow assertion).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PLUGIN_ROOT.parent.parent
GSR_TOOL = PLUGIN_ROOT / "scripts" / "tools" / "generate_security_report.py"

sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import run_scan_and_report  # noqa: E402


def _gsr(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GSR_TOOL), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd),
    )


def _degraded_input(tmp_path: Path) -> Path:
    p = tmp_path / "degraded.json"
    p.write_text(json.dumps({
        "findings": [],
        "degraded": True,
        "scan_errors": [
            {"scanner": "gitleaks", "reason": "empty_output", "detail": "FTL fatal"}
        ],
    }), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# generate_security_report.py — combined-report banner
# ---------------------------------------------------------------------------

class TestGenerateReportDegradedBanner:

    def test_standard_report_renders_banner(self, tmp_path: Path):
        md_out = tmp_path / "out.md"
        result = _gsr("--input", str(_degraded_input(tmp_path)),
                      "--output", str(md_out), cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        md = md_out.read_text(encoding="utf-8")
        assert "Degraded" in md
        assert "gitleaks" in md
        assert "empty_output" in md

    def test_pr_mode_renders_banner(self, tmp_path: Path):
        md_out = tmp_path / "out.md"
        result = _gsr("--input", str(_degraded_input(tmp_path)),
                      "--output", str(md_out), "--pr-mode", cwd=tmp_path)
        assert result.returncode == 0, result.stderr
        assert "Degraded" in md_out.read_text(encoding="utf-8")

    def test_json_sidecar_carries_degraded(self, tmp_path: Path):
        json_out = tmp_path / "out.json"
        _gsr("--input", str(_degraded_input(tmp_path)),
             "--json-output", str(json_out), cwd=tmp_path)
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        assert payload["degraded"] is True
        assert payload["scan_errors"][0]["scanner"] == "gitleaks"

    def test_clean_input_has_no_banner(self, tmp_path: Path):
        clean = tmp_path / "clean.json"
        clean.write_text(json.dumps({"findings": []}), encoding="utf-8")
        md_out = tmp_path / "out.md"
        _gsr("--input", str(clean), "--output", str(md_out), cwd=tmp_path)
        assert "Degraded" not in md_out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# run_scan_and_report.py — local report embeds degraded + exits non-zero
# ---------------------------------------------------------------------------

class TestRunScanReportDegraded:

    def _degraded_backend(self):
        backend = MagicMock()
        backend.name = "oss"
        backend.scan.return_value = []  # secrets leg degraded → 0 findings
        backend.scan_errors = [
            {"scanner": "gitleaks", "reason": "empty_output", "detail": "FTL fatal"}
        ]
        return backend

    def test_degraded_exits_nonzero_and_embeds_marker(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(run_scan_and_report, "get_backend", self._degraded_backend)
        rc = run_scan_and_report.run(project_root=tmp_path, repo="x/y", full_evidence=False)
        assert rc == 1  # degraded scan is not a clean success

        latest_json = tmp_path / ".shipwright" / "securityreports" / "latest.json"
        latest_md = tmp_path / ".shipwright" / "securityreports" / "latest.md"
        payload = json.loads(latest_json.read_text(encoding="utf-8"))
        assert payload["degraded"] is True
        assert payload["scan_errors"][0]["scanner"] == "gitleaks"
        assert "Degraded" in latest_md.read_text(encoding="utf-8")

    def test_clean_backend_is_not_degraded(self, monkeypatch, tmp_path: Path):
        backend = MagicMock()
        backend.name = "oss"
        backend.scan.return_value = []
        backend.scan_errors = []
        monkeypatch.setattr(run_scan_and_report, "get_backend", lambda: backend)
        rc = run_scan_and_report.run(project_root=tmp_path, repo="x/y", full_evidence=False)
        assert rc == 0
        payload = json.loads(
            (tmp_path / ".shipwright" / "securityreports" / "latest.json")
            .read_text(encoding="utf-8")
        )
        assert payload["degraded"] is False


# ---------------------------------------------------------------------------
# security.yml — the critical-gate fails closed on findings.json.degraded
# ---------------------------------------------------------------------------

class TestSecurityWorkflowDegradedGuard:

    def _gate_step_body(self) -> str:
        text = (REPO_ROOT / ".github" / "workflows" / "security.yml").read_text(
            encoding="utf-8"
        )
        # Crude but sufficient: the gate references findings.json + degraded.
        assert "Check for critical findings" in text, "critical-gate step missing"
        return text

    def test_gate_reads_degraded_field(self):
        text = self._gate_step_body()
        assert ".degraded" in text, (
            "security.yml critical-gate must inspect findings.json `.degraded` "
            "so a fataled scanner leg fails closed (the scan step is "
            "continue-on-error, so scan.py's exit code is ignored in CI)."
        )

    def test_gate_exits_on_degraded(self):
        """A `.degraded` read coupled to a non-zero `exit` within the gate."""
        text = self._gate_step_body()
        lines = text.splitlines()
        deg_idx = [i for i, ln in enumerate(lines) if "degraded" in ln.lower()
                   and "jq" in ln.lower()]
        assert deg_idx, "no `jq ... degraded` read found in security.yml"
        # An `exit 1` must appear within a few lines of the degraded read.
        coupled = any(
            any("exit 1" in lines[j] for j in range(i, min(i + 6, len(lines))))
            for i in deg_idx
        )
        assert coupled, "degraded read is not coupled to a fail-closed `exit 1`"

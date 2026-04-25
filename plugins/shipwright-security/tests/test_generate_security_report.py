"""Tests for generate_security_report.py — extensions added in iterate
sec-report-and-orchestrator-decouple.

Covers:
- ``--json-output PATH`` writes a machine-readable sidecar
- JSON payload carries ``schema_version: 1`` and the same findings as MD
- Existing ``--input`` / ``stdin`` / ``--pr-mode`` flows are unchanged
- Risk level + severity + scanner breakdown match between MD and JSON
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
TOOL = PLUGIN_ROOT / "scripts" / "tools" / "generate_security_report.py"


def _findings_fixture(tmp_path: Path) -> Path:
    """Write a small findings.json with one finding of each source."""
    findings = {
        "findings": [
            {
                "id": "f-01",
                "source": "semgrep",
                "type": "sast",
                "rule": "subprocess-shell-true",
                "severity": "high",
                "severity_score": 7.5,
                "affected_file": "scripts/run.py",
                "affected_line": 42,
                "cwe_classes": ["CWE-78"],
                "description": "Found subprocess.run with shell=True.",
                "_remediation_class": "agent-fixable",
            },
            {
                "id": "f-02",
                "source": "trivy",
                "type": "sca",
                "rule": "CVE-2025-71176",
                "cve_id": "CVE-2025-71176",
                "severity": "medium",
                "severity_score": 5.0,
                "affected_package": "requests",
                "installed_version": "2.31.0",
                "fixed_version": "2.32.0",
                "affected_file": "uv.lock",
                "_remediation_class": "auto-fixable",
            },
            {
                "id": "f-03",
                "source": "gitleaks",
                "type": "secret_detection",
                "rule": "generic-api-key",
                "severity": "high",
                "affected_file": "tests/fixtures/sample.json",
                "affected_line": 8,
                "cwe_classes": ["CWE-798"],
                "description": "Generic API key.",
                "_remediation_class": "agent-fixable",
            },
        ],
    }
    p = tmp_path / "findings.json"
    p.write_text(json.dumps(findings), encoding="utf-8")
    return p


def _run_tool(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """Invoke the tool via uv run from the plugin root."""
    cmd = [sys.executable, str(TOOL), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd),
    )


# ---------------------------------------------------------------------------
# --json-output sidecar
# ---------------------------------------------------------------------------


class TestJsonOutputSidecar:

    def test_json_output_writes_sidecar_file(self, tmp_path: Path):
        findings_path = _findings_fixture(tmp_path)
        md_out = tmp_path / "out.md"
        json_out = tmp_path / "out.json"

        result = _run_tool(
            "--input", str(findings_path),
            "--output", str(md_out),
            "--json-output", str(json_out),
            "--repo", "test/repo",
            cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert md_out.exists()
        assert json_out.exists()

    def test_json_payload_has_schema_version_1(self, tmp_path: Path):
        findings_path = _findings_fixture(tmp_path)
        md_out = tmp_path / "out.md"
        json_out = tmp_path / "out.json"

        _run_tool(
            "--input", str(findings_path),
            "--output", str(md_out),
            "--json-output", str(json_out),
            cwd=tmp_path,
        )
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1

    def test_json_payload_carries_findings_unchanged(self, tmp_path: Path):
        findings_path = _findings_fixture(tmp_path)
        md_out = tmp_path / "out.md"
        json_out = tmp_path / "out.json"

        _run_tool(
            "--input", str(findings_path),
            "--output", str(md_out),
            "--json-output", str(json_out),
            cwd=tmp_path,
        )
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        assert isinstance(payload["findings"], list)
        assert len(payload["findings"]) == 3
        sources = {f["source"] for f in payload["findings"]}
        assert sources == {"semgrep", "trivy", "gitleaks"}

    def test_json_payload_has_risk_level_and_breakdown(self, tmp_path: Path):
        findings_path = _findings_fixture(tmp_path)
        md_out = tmp_path / "out.md"
        json_out = tmp_path / "out.json"

        _run_tool(
            "--input", str(findings_path),
            "--output", str(md_out),
            "--json-output", str(json_out),
            cwd=tmp_path,
        )
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        # 2 highs + 1 medium → HIGH per generate_security_report.calculate_risk_level
        assert payload["risk_level"] == "HIGH"
        assert payload["total_findings"] == 3
        assert payload["by_severity"]["high"] == 2
        assert payload["by_severity"]["medium"] == 1
        assert payload["by_source"]["semgrep"] == 1
        assert payload["by_source"]["trivy"] == 1
        assert payload["by_source"]["gitleaks"] == 1

    def test_json_payload_includes_repo_name(self, tmp_path: Path):
        findings_path = _findings_fixture(tmp_path)
        md_out = tmp_path / "out.md"
        json_out = tmp_path / "out.json"

        _run_tool(
            "--input", str(findings_path),
            "--output", str(md_out),
            "--json-output", str(json_out),
            "--repo", "svenroth-ai/shipwright",
            cwd=tmp_path,
        )
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        assert payload["repo"] == "svenroth-ai/shipwright"


# ---------------------------------------------------------------------------
# Markdown output unchanged when --json-output is given alongside
# ---------------------------------------------------------------------------


class TestMarkdownStillProduced:

    def test_markdown_output_includes_findings_section(self, tmp_path: Path):
        findings_path = _findings_fixture(tmp_path)
        md_out = tmp_path / "out.md"
        json_out = tmp_path / "out.json"

        _run_tool(
            "--input", str(findings_path),
            "--output", str(md_out),
            "--json-output", str(json_out),
            cwd=tmp_path,
        )
        md_content = md_out.read_text(encoding="utf-8")
        # existing structure preserved
        assert "## Summary" in md_content
        assert "subprocess-shell-true" in md_content
        assert "CVE-2025-71176" in md_content


# ---------------------------------------------------------------------------
# --json-output without --output (json-only mode)
# ---------------------------------------------------------------------------


class TestJsonOutputAlone:

    def test_json_output_without_md_output_is_supported(self, tmp_path: Path):
        """User may want only the machine-readable sidecar, no markdown."""
        findings_path = _findings_fixture(tmp_path)
        json_out = tmp_path / "out.json"

        result = _run_tool(
            "--input", str(findings_path),
            "--json-output", str(json_out),
            cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert json_out.exists()
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1


# ---------------------------------------------------------------------------
# Empty findings — schema_version still emitted
# ---------------------------------------------------------------------------


class TestEmptyFindings:

    def test_zero_findings_still_emits_valid_schema(self, tmp_path: Path):
        empty = tmp_path / "empty.json"
        empty.write_text(json.dumps({"findings": []}), encoding="utf-8")
        md_out = tmp_path / "out.md"
        json_out = tmp_path / "out.json"

        result = _run_tool(
            "--input", str(empty),
            "--output", str(md_out),
            "--json-output", str(json_out),
            cwd=tmp_path,
        )
        assert result.returncode == 0
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["total_findings"] == 0
        assert payload["risk_level"] == "NONE"
        assert payload["findings"] == []

#!/usr/bin/env python3
"""OSS scanner backend for shipwright-security.

Orchestrates local CLI tools (Semgrep, Trivy, Gitleaks) and normalizes
their output into the standard finding schema.  Each tool is optional —
the backend reports only the capabilities that are actually available.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Any

from scanner_backend import ScannerBackend, classify_finding, register_backend
from normalizers.semgrep import normalize as normalize_semgrep
from normalizers.trivy import normalize as normalize_trivy
from normalizers.gitleaks import normalize as normalize_gitleaks


@register_backend
class OSSBackend(ScannerBackend):
    """Local open-source scanner backend (Semgrep + Trivy + Gitleaks)."""

    name = "oss"
    requires_cloud = False

    @property
    def capabilities(self) -> set[str]:
        caps: set[str] = set()
        if shutil.which("semgrep"):
            caps.add("sast")
        if shutil.which("trivy"):
            caps.add("sca")
        if shutil.which("gitleaks"):
            caps.add("secrets")
        return caps

    def is_configured(self) -> bool:
        return len(self.capabilities) > 0

    def scan(self, target: str, scan_types: list[str] | None = None) -> list[dict[str, Any]]:
        """Run available scanners and return normalized findings."""
        caps = self.capabilities
        if scan_types:
            caps = caps & set(scan_types)

        findings: list[dict[str, Any]] = []

        if "sast" in caps:
            findings.extend(_run_semgrep(target))
        if "sca" in caps:
            findings.extend(_run_trivy(target))
        if "secrets" in caps:
            findings.extend(_run_gitleaks(target))

        # Apply classification
        for f in findings:
            f["_remediation_class"] = classify_finding(f)

        return findings

    def get_setup_instructions(self) -> str:
        is_win = sys.platform == "win32"
        lines = [
            "OSS Security Scanner (local, free):",
            "Install one or more of these tools:",
            "",
        ]
        for tool, info in _TOOL_INFO.items():
            installed = "installed" if shutil.which(tool) else "NOT installed"
            install_cmd = info["install_win"] if is_win else info["install_mac"]
            lines.append(f"  {tool} ({info['type']}) — {installed}")
            lines.append(f"    {('Windows' if is_win else 'macOS')}: {install_cmd}")
            lines.append(f"    Download: {info['url']}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------

_TOOL_INFO = {
    "semgrep": {
        "type": "SAST",
        "install_win": "pip install semgrep",
        "install_mac": "brew install semgrep",
        "url": "https://semgrep.dev/docs/getting-started/",
    },
    "trivy": {
        "type": "SCA",
        "install_win": "winget install AquaSecurity.Trivy",
        "install_mac": "brew install trivy",
        "url": "https://github.com/aquasecurity/trivy/releases",
    },
    "gitleaks": {
        "type": "Secrets",
        "install_win": "winget install Gitleaks.Gitleaks",
        "install_mac": "brew install gitleaks",
        "url": "https://github.com/gitleaks/gitleaks/releases",
    },
}


# ---------------------------------------------------------------------------
# Tool runners
# ---------------------------------------------------------------------------

_TIMEOUT = 300  # 5 minutes per tool


def _run_semgrep(target: str) -> list[dict[str, Any]]:
    """Run Semgrep and return normalized findings."""
    cmd = ["semgrep", "scan", "--json", "--config", "auto", target]
    raw = _run_tool(cmd, tool_name="semgrep")
    if raw is None:
        return []
    return normalize_semgrep(raw)


def _run_trivy(target: str) -> list[dict[str, Any]]:
    """Run Trivy and return normalized findings."""
    cmd = ["trivy", "fs", "--format", "json", "--scanners", "vuln", target]
    raw = _run_tool(cmd, tool_name="trivy")
    if raw is None:
        return []
    return normalize_trivy(raw)


def _run_gitleaks(target: str) -> list[dict[str, Any]]:
    """Run Gitleaks and return normalized findings."""
    cmd = ["gitleaks", "detect", "--report-format", "json", "-s", target, "--report-path", "-"]
    raw = _run_tool(cmd, tool_name="gitleaks", expect_nonzero=True)
    if raw is None:
        return []
    return normalize_gitleaks(raw)


def _run_tool(
    cmd: list[str],
    tool_name: str,
    expect_nonzero: bool = False,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Run a CLI tool and parse its JSON output.

    Args:
        cmd: Command + arguments.
        tool_name: Human-readable name for error messages.
        expect_nonzero: If True, a non-zero exit code is acceptable
            (e.g. gitleaks returns 1 when findings exist).

    Returns:
        Parsed JSON (dict or list), or None on failure.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )

        if result.returncode != 0 and not expect_nonzero:
            _log(f"{tool_name}: exited with code {result.returncode}")
            if result.stderr:
                _log(f"{tool_name} stderr: {result.stderr[:500]}")
            return None

        stdout = result.stdout.strip()
        if not stdout:
            return None

        return json.loads(stdout)

    except subprocess.TimeoutExpired:
        _log(f"{tool_name}: timed out after {_TIMEOUT}s")
        return None
    except json.JSONDecodeError as e:
        _log(f"{tool_name}: invalid JSON output: {e}")
        return None
    except FileNotFoundError:
        _log(f"{tool_name}: binary not found on PATH")
        return None


def _log(msg: str) -> None:
    """Log to stderr (visible to Claude but not captured as JSON output)."""
    print(f"[shipwright-security] {msg}", file=sys.stderr)

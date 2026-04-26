#!/usr/bin/env python3
"""OSS scanner backend for shipwright-security.

Orchestrates local CLI tools (Semgrep, Trivy, Gitleaks) and normalizes
their output into the standard finding schema.  Each tool is optional —
the backend reports only the capabilities that are actually available.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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

# Directories always skipped: build artifacts, dependency trees, VCS, caches.
# Scanning these produces timeouts (Semgrep on node_modules) and noise about
# third-party code we don't own. Users extend — never replace — via
# SHIPWRIGHT_SCAN_EXCLUDES.
_DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".venv",
    "node_modules",
    ".git",
    ".pytest_cache",
    "dist",
    "build",
    ".next",
    "__pycache__",
    ".cache",
    ".shipwright",     # canonical hidden dir for shipwright artifacts
    "securityreports", # legacy pre-iterate-3 location, kept one cycle for migrating projects
)

# Env-var additions must be simple folder names: letters, digits, underscore,
# dot, hyphen. Rejects glob wildcards, path separators, and parent traversal
# so a CI-config edit cannot weaken the scan by excluding real source dirs.
_SIMPLE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_FORBIDDEN_NAMES = frozenset({".", ".."})


def _resolve_excludes() -> tuple[str, ...]:
    """Return defaults plus validated SHIPWRIGHT_SCAN_EXCLUDES entries."""
    extras_raw = os.environ.get("SHIPWRIGHT_SCAN_EXCLUDES", "")
    defaults = list(_DEFAULT_EXCLUDES)
    if not extras_raw.strip():
        return tuple(defaults)

    seen = set(defaults)
    for candidate in extras_raw.split(","):
        name = candidate.strip()
        if not name:
            continue
        if name in _FORBIDDEN_NAMES or not _SIMPLE_NAME_RE.match(name):
            _log(f"ignoring invalid exclude pattern: {name!r}")
            continue
        if name in seen:
            continue
        defaults.append(name)
        seen.add(name)
    return tuple(defaults)


def _run_semgrep(target: str) -> list[dict[str, Any]]:
    """Run Semgrep and return normalized findings."""
    cmd = ["semgrep", "scan", "--json", "--config", "auto"]
    for name in _resolve_excludes():
        cmd.extend(["--exclude", name])
    cmd.append(target)
    raw = _run_tool(cmd, tool_name="semgrep")
    if raw is None:
        return []
    return normalize_semgrep(raw)


def _run_trivy(target: str) -> list[dict[str, Any]]:
    """Run Trivy and return normalized findings."""
    cmd = ["trivy", "fs", "--format", "json", "--scanners", "vuln"]
    for name in _resolve_excludes():
        cmd.extend(["--skip-dirs", name])
    cmd.append(target)
    raw = _run_tool(cmd, tool_name="trivy")
    if raw is None:
        return []
    return normalize_trivy(raw)


def _run_gitleaks(target: str) -> list[dict[str, Any]]:
    """Run Gitleaks and return normalized findings.

    Gitleaks has no --exclude flag; path exclusions go through a TOML config
    with [allowlist] paths regex entries. A temp config is generated per
    invocation and cleaned up after the subprocess returns.
    """
    config_path = _write_gitleaks_allowlist(_resolve_excludes())
    try:
        cmd = [
            "gitleaks", "detect",
            "--report-format", "json",
            "-s", target,
            "--report-path", "-",
            "--config", config_path,
        ]
        raw = _run_tool(cmd, tool_name="gitleaks", expect_nonzero=True)
    finally:
        try:
            os.unlink(config_path)
        except OSError:
            pass
    if raw is None:
        return []
    return normalize_gitleaks(raw)


def _write_gitleaks_allowlist(excludes: tuple[str, ...]) -> str:
    """Write a temp gitleaks config that allowlists the given folder names.

    Uses [extend] useDefault = true so gitleaks' built-in rules still apply,
    then adds [allowlist] paths entries matching each excluded folder as a
    path segment (anchored to segment boundary, not substring).
    """
    # TOML single-quote literal strings: no escape processing, so backslashes
    # in the regex pass through verbatim. _SIMPLE_NAME_RE already blocks every
    # non-[A-Za-z0-9_.-] char (including single quotes), so name interpolation
    # is safe here.
    patterns = [f"'(^|/){re.escape(name)}(/|$)'" for name in excludes]
    body = (
        "# Auto-generated by shipwright-security — do not edit manually.\n"
        'title = "shipwright allowlist"\n'
        "\n"
        "[extend]\n"
        "useDefault = true\n"
        "\n"
        "[allowlist]\n"
        'description = "shipwright default scanner exclusions"\n'
        f"paths = [{', '.join(patterns)}]\n"
    )
    fd, path = tempfile.mkstemp(suffix=".toml", prefix="shipwright-gitleaks-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    return path


def _utf8_subprocess_env() -> dict[str, str]:
    """Env for scanner subprocesses with UTF-8 IO forced.

    Semgrep is a Python tool; on Windows its internal sys.stdout/stderr
    default to cp1252 and crash when scanning files with Unicode control
    chars (e.g. \\u202a LEFT-TO-RIGHT EMBEDDING). PYTHONIOENCODING=utf-8
    and PYTHONUTF8=1 fix that. Trivy and Gitleaks are Go binaries so these
    vars are no-ops there, but passing a single consistent env keeps the
    subprocess contract simple.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


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
            encoding="utf-8",
            errors="replace",
            env=_utf8_subprocess_env(),
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

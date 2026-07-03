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
from semgrep_tailoring import normalize_tailored as normalize_semgrep
from normalizers.trivy import normalize as normalize_trivy
from normalizers.gitleaks import normalize as normalize_gitleaks


@register_backend
class OSSBackend(ScannerBackend):
    """Local open-source scanner backend (Semgrep + Trivy + Gitleaks)."""

    name = "oss"
    requires_cloud = False
    # scan_errors (degraded-leg markers) is declared + documented on the
    # ScannerBackend ABC; scan() (re)populates it per call.

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
        """Run available scanners and return normalized findings.

        Degraded legs (a scanner that was invoked but produced no parseable
        output) are recorded on ``self.scan_errors`` rather than silently
        collapsing to ``[]`` findings. The findings list stays a pure
        data-plane channel; ``scan_errors`` is the control-plane signal a
        consumer reads via ``getattr(backend, "scan_errors", [])``.
        """
        caps = self.capabilities
        if scan_types:
            caps = caps & set(scan_types)

        findings: list[dict[str, Any]] = []
        # Reset per call so a second scan() never inherits the first's markers.
        self.scan_errors = []

        if "sast" in caps:
            findings.extend(_run_semgrep(target, self.scan_errors))
        if "sca" in caps:
            findings.extend(_run_trivy(target, self.scan_errors))
        if "secrets" in caps:
            findings.extend(_run_gitleaks(target, self.scan_errors))

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

# Closed vocabulary of degraded-scan reasons recorded on the ``scan_errors``
# channel. Every ``None``-return branch of ``_run_tool`` maps to exactly one of
# these. The report/gate layer relies on this set being exhaustive (a meta-test
# asserts every emitted reason is a member).
#   nonzero_exit  : unexpected non-zero exit (expect_nonzero=False), e.g. a
#                   semgrep/trivy crash.
#   empty_output  : the tool exited but produced no parseable payload — a
#                   gitleaks fatal (exit 1, empty report) or a semgrep/trivy
#                   empty stdout. A *clean* leg never reaches here: it emits a
#                   non-empty JSON envelope ({"results":[]} / []).
#   timeout       : killed by the per-tool timeout.
#   invalid_json  : payload present but not valid JSON (truncated/garbage).
#   missing_binary: the binary vanished from PATH between capability probe and
#                   invocation (FileNotFoundError).
SCAN_ERROR_REASONS: tuple[str, ...] = (
    "nonzero_exit",
    "empty_output",
    "timeout",
    "invalid_json",
    "missing_binary",
)

# Per-scanner exclusion contract (Sub-Iterate H, Pfad B').
#
# Gitignore is the single source of truth for "what should the scanner
# look at". Per-scanner lists below cover only what the tool itself
# cannot resolve from gitignore.
#
# Semgrep:  empty list. Semgrep ships .semgrepignore (covers
#           node_modules/build/dist/vendor/.venv/.tox/.npm/.yarn etc.) AND
#           respects the project .gitignore for untracked files. Adding
#           plugin-side excludes would either duplicate built-ins or
#           silently override user gitignore decisions.
# Trivy:    conservative cross-language build/dependency list. Trivy has
#           no .gitignore awareness, so without an explicit list it
#           crawls node_modules / target / vendor / etc.
# Gitleaks: same conservative list, applied as a generated TOML
#           [allowlist] paths array. Gitleaks has no --exclude flag and
#           also ignores .gitignore in detect-mode.
#
# What is NOT in any list anymore:
#   - .shipwright       (was the H trigger — silently skipped agent_docs)
#   - securityreports   (legacy pre-iterate-3 location, deprecation done)
# Projects that want them skipped: gitignore them (Semgrep) or set
# SHIPWRIGHT_SCAN_EXCLUDES (Trivy/Gitleaks).

_SEMGREP_EXCLUDES: tuple[str, ...] = ()

_TRIVY_EXCLUDES: tuple[str, ...] = (
    # Python
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "__pycache__",
    # JS/TS
    "node_modules",
    ".next",
    # VCS + generic caches
    ".git",
    ".cache",
    # Generic build outputs
    "dist",
    "build",
    # Polyglot build/dep dirs (Reviewer-Finding 4: Java/.NET/Go/Ruby/Terraform/nix)
    "target",       # Rust + Java (Maven)
    "bin",          # .NET
    "obj",          # .NET
    "vendor",       # Go, PHP, Ruby
    ".gradle",      # Java/Kotlin
    ".terraform",   # Terraform
    ".direnv",      # nix-direnv
    # Coverage outputs
    "coverage",
    "htmlcov",
    # Shipwright-canonical parallel-iterate worktree path (gitignored
    # by convention; surfaced as Trivy noise during H.D.5 benchmark
    # because Trivy and Gitleaks do not honor .gitignore — 13
    # false-positives in stale parallel-iterate node_modules).
    ".worktrees",
)

# Gitleaks scans the same dependency/build trees as Trivy.
_GITLEAKS_EXCLUDES: tuple[str, ...] = _TRIVY_EXCLUDES

_SCANNER_EXCLUDES: dict[str, tuple[str, ...]] = {
    "semgrep": _SEMGREP_EXCLUDES,
    "trivy": _TRIVY_EXCLUDES,
    "gitleaks": _GITLEAKS_EXCLUDES,
}

# Env-var additions must be simple folder names: letters, digits, underscore,
# dot, hyphen. Rejects glob wildcards, path separators, and parent traversal
# so a CI-config edit cannot weaken the scan by excluding real source dirs.
_SIMPLE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_FORBIDDEN_NAMES = frozenset({".", ".."})


def _resolve_excludes(scanner: str) -> tuple[str, ...]:
    """Return scanner-specific defaults plus validated SHIPWRIGHT_SCAN_EXCLUDES.

    The env var extends every scanner uniformly — simplest semantics and keeps
    the validation logic centralized. Per-scanner env overrides (e.g.
    SHIPWRIGHT_TRIVY_EXCLUDES) are intentionally not supported in v1.
    """
    if scanner not in _SCANNER_EXCLUDES:
        raise ValueError(
            f"Unknown scanner: {scanner!r}. "
            f"Expected one of: {sorted(_SCANNER_EXCLUDES)}"
        )
    defaults = list(_SCANNER_EXCLUDES[scanner])

    extras_raw = os.environ.get("SHIPWRIGHT_SCAN_EXCLUDES", "")
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


def _run_semgrep(
    target: str, errors: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run Semgrep and return normalized findings.

    ``errors`` (when provided) is the degraded-scan accumulator; a degraded
    leg appends one marker to it and still returns ``[]`` findings.
    """
    cmd = ["semgrep", "scan", "--json", "--config", "auto"]
    for name in _resolve_excludes("semgrep"):
        cmd.extend(["--exclude", name])
    cmd.append(target)
    raw = _run_tool(cmd, tool_name="semgrep", errors=errors)
    if raw is None:
        return []
    return normalize_semgrep(raw)


def _resolve_trivy_ignorefile(target: str) -> str | None:
    """Return a Trivy ignore file at the SCANNED target root, if present.

    This is the accepted-risk register for SCA findings. Prefers the rich
    ``.trivyignore.yaml`` (``vulnerabilities[].{id,paths,expired_at,statement}``
    — scoped + time-bounded, documented acceptances) over the classic flat
    ``.trivyignore``. Keyed to the scanned ``target``, NOT Trivy's working
    directory: Trivy only auto-detects an ignore file in its CWD, which differs
    between CI (``plugins/shipwright-security``) and a local / adopted-repo run
    (the project root), so auto-detection is unreliable. Passing
    ``--ignorefile`` explicitly makes the register live at the project root in
    every context (and gives adopted repos the same first-class mechanism).
    """
    for name in (".trivyignore.yaml", ".trivyignore.yml", ".trivyignore"):
        candidate = os.path.join(target, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def _run_trivy(
    target: str, errors: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run Trivy and return normalized findings (see ``_run_semgrep`` for
    the ``errors`` accumulator contract)."""
    cmd = ["trivy", "fs", "--format", "json", "--scanners", "vuln"]
    ignorefile = _resolve_trivy_ignorefile(target)
    if ignorefile:
        cmd.extend(["--ignorefile", ignorefile])
    for name in _resolve_excludes("trivy"):
        cmd.extend(["--skip-dirs", name])
    cmd.append(target)
    raw = _run_tool(cmd, tool_name="trivy", errors=errors)
    if raw is None:
        return []
    return normalize_trivy(raw)


def _run_gitleaks(
    target: str, errors: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run Gitleaks and return normalized findings.

    Gitleaks has no --exclude flag; path exclusions go through a TOML config
    with [allowlist] paths regex entries. It also has no stdout-report mode:
    ``--report-path -`` is NOT special-cased to stdout — gitleaks does
    ``os.Create("-")`` and writes the JSON to a literal file named ``-``
    (verified against v8.21.2 ``cmd/root.go::findingSummaryAndExit`` +
    ``report/report.go::Write``). The old ``--report-path -`` therefore made
    the wrapper read empty stdout and silently return 0 findings on every
    platform (iterate-2026-06-05). So the report is written to a real temp
    file and read back here. Both temp files are generated per invocation and
    cleaned up afterward.
    """
    config_path = _write_gitleaks_allowlist(_resolve_excludes("gitleaks"))
    report_fd, report_path = tempfile.mkstemp(
        suffix=".json", prefix="shipwright-gitleaks-report-"
    )
    os.close(report_fd)  # gitleaks re-creates (truncates) this path itself
    try:
        cmd = [
            "gitleaks", "detect",
            "--report-format", "json",
            "-s", target,
            "--report-path", report_path,
            "--config", config_path,
        ]
        raw = _run_tool(
            cmd,
            tool_name="gitleaks",
            expect_nonzero=True,
            report_path=report_path,
            errors=errors,
        )
    finally:
        for tmp in (config_path, report_path):
            try:
                os.unlink(tmp)
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
        # Defense-in-depth: the famous magic-hex placeholder cafebabe:deadbeef
        # false-matches the built-in sidekiq-secret rule but is never a real
        # secret. Allowlisting it here keeps the monorepo's own gitleaks scan
        # from false-redding on it, mirroring the adopt-scaffolded
        # shared/templates/github-actions/gitleaks.toml.template. useDefault
        # above keeps every real secret rule live.
        '# magic-hex placeholder (cafebabe:deadbeef) — false sidekiq-secret match\n'
        'regexTarget = "match"\n'
        "regexes = ['''cafebabe:deadbeef''']\n"
        'stopwords = ["cafebabe", "deadbeef"]\n'
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


def _read_report_file(path: str) -> str:
    """Read a tool's JSON report file, returning its stripped content.

    Returns an empty string if the file is missing or unreadable — the
    caller treats that as "no parseable output" and surfaces stderr.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def _record_scan_error(
    errors: list[dict[str, Any]] | None,
    tool_name: str,
    reason: str,
    detail: str,
) -> None:
    """Append one degraded-leg marker to the ``errors`` accumulator.

    No-op when ``errors`` is None (direct callers that don't track degradation).
    ``reason`` must be a member of ``SCAN_ERROR_REASONS``; ``detail`` is
    truncated to keep the marker small enough to ride in ``findings.json``.
    """
    if errors is None:
        return
    errors.append({
        "scanner": tool_name,
        "reason": reason,
        "detail": (detail or "").strip()[:500],
    })


def _run_tool(
    cmd: list[str],
    tool_name: str,
    expect_nonzero: bool = False,
    report_path: str | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Run a CLI tool and parse its JSON output.

    Args:
        cmd: Command + arguments.
        tool_name: Human-readable name for error messages.
        expect_nonzero: If True, a non-zero exit code is acceptable
            (e.g. gitleaks returns 1 when findings exist).
        report_path: If set, the tool writes its JSON report to this file
            path and the parsed file content is returned (rather than
            parsing stdout). Gitleaks requires this: it has no stdout-report
            mode — ``--report-path -`` writes to a literal file named ``-``,
            never to stdout (see ``_run_gitleaks``). Semgrep / Trivy leave
            this None and emit JSON on stdout natively.
        errors: Optional degraded-scan accumulator. EVERY ``None`` return below
            is a degraded leg (the tool was invoked but produced no parseable
            output) and records exactly one marker here. A clean leg returns
            parsed JSON and records nothing. This is what lets ``scan()``
            distinguish "ran clean → 0 findings" from "fataled → 0 findings".

    Returns:
        Parsed JSON (dict or list), or None on failure (degraded).
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
            _record_scan_error(
                errors, tool_name, "nonzero_exit",
                f"exit {result.returncode}: {result.stderr or ''}",
            )
            return None

        if report_path is not None:
            payload = _read_report_file(report_path)
        else:
            payload = result.stdout.strip()

        if not payload:
            # No parseable output. When a non-zero exit is "expected"
            # (gitleaks exits 1 both on findings AND on fatal errors via
            # log.Fatal), an empty payload is ambiguous — surface stderr so a
            # silent tool failure is not mistaken for a clean "0 findings".
            if result.stderr and result.stderr.strip():
                _log(f"{tool_name} stderr: {result.stderr[:500]}")
            _record_scan_error(
                errors, tool_name, "empty_output",
                f"no parseable output (exit {result.returncode}): "
                f"{result.stderr or ''}",
            )
            return None

        return json.loads(payload)

    except subprocess.TimeoutExpired:
        _log(f"{tool_name}: timed out after {_TIMEOUT}s")
        _record_scan_error(
            errors, tool_name, "timeout", f"timed out after {_TIMEOUT}s",
        )
        return None
    except json.JSONDecodeError as e:
        _log(f"{tool_name}: invalid JSON output: {e}")
        _record_scan_error(errors, tool_name, "invalid_json", str(e))
        return None
    except FileNotFoundError:
        _log(f"{tool_name}: binary not found on PATH")
        _record_scan_error(
            errors, tool_name, "missing_binary", "binary not found on PATH",
        )
        return None


def _log(msg: str) -> None:
    """Log to stderr (visible to Claude but not captured as JSON output)."""
    print(f"[shipwright-security] {msg}", file=sys.stderr)

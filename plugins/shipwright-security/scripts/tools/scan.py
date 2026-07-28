#!/usr/bin/env python3
"""CLI wrapper around the shipwright-security OSS scanner backend.

Runs Semgrep / Trivy / Gitleaks against a target path and writes normalized
findings to a JSON file. Designed to be invoked from GitHub Actions or locally
before pushing.

Usage:
    uv run scripts/tools/scan.py \
        --path . \
        --output findings.json \
        --scan-types sast,sca,secret-detection \
        [--fail-on critical,high]

Exit codes:
    0  no findings above --fail-on threshold
    1  findings above threshold
    2  scan error (backend not available, unexpected failure)
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _fix_windows_encoding() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent.parent
SHARED_ROOT = PLUGIN_ROOT.parent.parent / "shared"

sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(SHARED_ROOT / "scripts"))

try:
    from lib.errors import structured_error, structured_success  # type: ignore
except (ImportError, ModuleNotFoundError):
    def structured_error(what_failed, what_was_attempted, error_category, is_retryable,
                         partial_results=None, alternatives=None, context=None):
        return {
            "success": False,
            "error": {
                "what_failed": what_failed,
                "what_was_attempted": what_was_attempted,
                "error_category": error_category,
                "is_retryable": is_retryable,
                "partial_results": partial_results or {},
                "alternatives": alternatives or [],
                "context": context or {},
            },
        }

    def structured_success(data=None):
        result = {"success": True}
        if data:
            result.update(data)
        return result


# Module-level import so tests can patch `scan.get_backend`.
try:
    from scanner_backend import get_backend  # type: ignore
    import oss_backend  # noqa: F401  # registers OSSBackend via decorator
    try:
        import aikido_client  # noqa: F401  # registers AikidoBackend if present
    except ImportError:
        pass
    _BACKEND_IMPORT_ERROR: str | None = None
except ImportError as _e:
    _BACKEND_IMPORT_ERROR = str(_e)

    def get_backend(name=None):  # type: ignore[misc]
        raise RuntimeError(f"scanner_backend unavailable: {_BACKEND_IMPORT_ERROR}")


try:
    from sarif_outputs import write_sarif_outputs as _write_sarif_outputs  # type: ignore
    _SARIF_IMPORT_ERROR: str | None = None
except ImportError as _e:
    _SARIF_IMPORT_ERROR = str(_e)

    def _write_sarif_outputs(findings, sarif_dir):  # type: ignore[misc]
        raise RuntimeError(f"sarif_writer unavailable: {_SARIF_IMPORT_ERROR}")


# Coverage manifest: DERIVED from capabilities, so nothing can forget it.
from coverage_sanitize import sanitize_coverage  # noqa: E402
from gitleaks_config import class_degradations as gitleaks_degradations  # noqa: E402
from scan_coverage import build_coverage  # noqa: E402


SCAN_TYPE_ALIASES = {
    "secret-detection": "secrets",
    "secret_detection": "secrets",
    "secrets": "secrets",
    "sast": "sast",
    "sca": "sca",
}

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


def parse_scan_types(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    resolved: list[str] = []
    for p in parts:
        if p not in SCAN_TYPE_ALIASES:
            raise ValueError(
                f"Unknown scan type '{p}'. Valid types: sast, sca, secret-detection"
            )
        resolved.append(SCAN_TYPE_ALIASES[p])
    return resolved


def parse_fail_on(raw: str | None) -> set[str]:
    if not raw:
        return set()
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    for p in parts:
        if p not in SEVERITY_ORDER:
            raise ValueError(
                f"Unknown severity '{p}'. Valid: {', '.join(SEVERITY_ORDER)}"
            )
    return set(parts)


def build_config(
    findings: list[dict[str, Any]],
    repo: str,
    scanner: str,
    scan_errors: list[dict[str, Any]] | None = None,
    coverage: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a shipwright_security_config.json compatible dict.

    ``scan_errors`` carries degraded-leg markers (see oss_backend.scan_errors).
    A non-empty list sets ``degraded: true`` so the CI critical-gate (which
    reads this file via jq) can fail closed even when ``findings`` is empty —
    a scanner that fataled must not read as a clean 0-findings scan.

    ``coverage`` is the complementary channel for the tool that was never there
    at all: one row per weakness class saying whether it was checked. A crashed
    tool already fails the run; an absent one used to be invisible, so a machine
    with one scanner produced a report that read clean for every class. This
    field is what a downstream gate (and ``scan_compare``) reads to know what
    the run can honestly claim. Additive — existing readers are unaffected.
    """
    errors = list(scan_errors or [])
    severity_counts = Counter(f.get("severity", "unknown") for f in findings)
    return {
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        "scanner": scanner,
        "total_findings": len(findings),
        "by_severity": {sev: severity_counts.get(sev, 0) for sev in SEVERITY_ORDER},
        "degraded": bool(errors),
        "scan_errors": errors,
        "coverage": list(coverage or []),
        "remediation": {
            "fixed": 0,
            "declined": 0,
            "deferred": 0,
            "open": len(findings),
        },
        "findings": findings,
    }


def count_above_threshold(findings: list[dict[str, Any]], fail_on: set[str]) -> int:
    if not fail_on:
        return 0
    return sum(1 for f in findings if f.get("severity", "").lower() in fail_on)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the OSS security scanner (Semgrep / Trivy / Gitleaks)",
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Target directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--output",
        help="Output JSON file path. If omitted, prints JSON to stdout.",
    )
    parser.add_argument(
        "--scan-types",
        help="Comma-separated list of scan types: sast, sca, secret-detection. "
             "Default: all available.",
    )
    parser.add_argument(
        "--fail-on",
        help="Comma-separated severities that cause exit code 1 when found. "
             "Example: --fail-on critical,high",
    )
    parser.add_argument(
        "--repo",
        default="unknown",
        help="Repository name for the config report header",
    )
    parser.add_argument(
        "--backend",
        default="oss",
        choices=["oss", "aikido"],
        help="Scanner backend to use (default: oss)",
    )
    parser.add_argument(
        "--sarif-dir",
        help="Directory to write per-source SARIF 2.1.0 files (one .sarif per scanner). "
             "Always emits a placeholder file for known scanners on clean scans so "
             "GitHub Actions upload-sarif doesn't fail on an empty directory.",
    )
    parser.add_argument(
        "--input-from-cache",
        help="Path to a previously-written findings.json. When provided AND the "
             "file exists, skip scanning entirely and reuse those findings. "
             "Used by CI to avoid double-scanning between report and SARIF steps.",
    )
    args = parser.parse_args()

    try:
        scan_types = parse_scan_types(args.scan_types)
        fail_on = parse_fail_on(args.fail_on)
    except ValueError as e:
        print(
            json.dumps(
                structured_error(
                    what_failed=str(e),
                    what_was_attempted="parse CLI arguments",
                    error_category="validation",
                    is_retryable=False,
                )
            ),
            file=sys.stderr,
        )
        return 2

    target = Path(args.path).resolve()
    if not target.exists():
        print(
            json.dumps(
                structured_error(
                    what_failed=f"Target path does not exist: {target}",
                    what_was_attempted=f"scan path {args.path}",
                    error_category="validation",
                    is_retryable=False,
                )
            ),
            file=sys.stderr,
        )
        return 2

    cache_path: Path | None = None
    if args.input_from_cache:
        cache_path = Path(args.input_from_cache).resolve()

    backend_name = args.backend
    backend_capabilities: set[str] | None = None
    scan_errors: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []

    if cache_path and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(
                json.dumps(
                    structured_error(
                        what_failed=f"Failed to load --input-from-cache: {e}",
                        what_was_attempted=f"read findings cache at {cache_path}",
                        error_category="validation",
                        is_retryable=False,
                    )
                ),
                file=sys.stderr,
            )
            return 2
        findings = cached.get("findings", []) if isinstance(cached, dict) else []
        backend_name = (cached.get("scanner") if isinstance(cached, dict) else None) or backend_name
        # Round-trip the degraded markers so the SARIF re-read (which reuses
        # this cache) keeps failing closed rather than re-emitting a clean scan.
        if isinstance(cached, dict):
            cached_errors = cached.get("scan_errors")
            scan_errors = list(cached_errors) if isinstance(cached_errors, list) else []
            # Same round-trip for the manifest, SANITIZED: the cache file is
            # caller-supplied, so re-emitting its rows verbatim would launder
            # untrusted labels into a fresh artifact.
            coverage = sanitize_coverage(cached.get("coverage"))
    else:
        try:
            backend = get_backend(args.backend)
        except RuntimeError as e:
            print(
                json.dumps(
                    structured_error(
                        what_failed=str(e),
                        what_was_attempted=f"initialize '{args.backend}' scanner backend",
                        error_category="business",
                        is_retryable=False,
                        alternatives=[
                            "Install Semgrep: pip install semgrep",
                            "Install Trivy: https://github.com/aquasecurity/trivy/releases",
                            "Install Gitleaks: https://github.com/gitleaks/gitleaks/releases",
                        ],
                    )
                ),
                file=sys.stderr,
            )
            return 2

        try:
            findings = backend.scan(str(target), scan_types=scan_types)
        except Exception as e:  # noqa: BLE001 — scanner errors are varied
            print(
                json.dumps(
                    structured_error(
                        what_failed=f"Scanner raised an exception: {e}",
                        what_was_attempted=f"run {args.backend} backend scan",
                        error_category="transient",
                        is_retryable=True,
                    )
                ),
                file=sys.stderr,
            )
            return 2

        backend_capabilities = getattr(backend, "capabilities", None)
        # Degraded-leg markers (empty for backends/mocks that never set them).
        raw_errors = getattr(backend, "scan_errors", [])
        scan_errors = list(raw_errors) if isinstance(raw_errors, list) else []
        caps = backend_capabilities if isinstance(
            backend_capabilities, (set, frozenset, list, tuple)) else ()
        # OSS-only degradations: Aikido runs its own secret scan, so this
        # repo's .gitleaks.toml says nothing about what it examined.
        coverage = build_coverage(
            available=caps, requested=scan_types, scan_errors=scan_errors,
            class_degradations=(
                gitleaks_degradations(str(target)) if backend_name == "oss" else {}),
        )

    config = build_config(
        findings, repo=args.repo, scanner=backend_name,
        scan_errors=scan_errors, coverage=coverage,
    )

    if args.sarif_dir:
        try:
            _write_sarif_outputs(findings, Path(args.sarif_dir).resolve())
        except Exception as e:  # noqa: BLE001 — best-effort, never abort scan
            print(
                json.dumps(
                    structured_error(
                        what_failed=f"SARIF write failed: {e}",
                        what_was_attempted=f"write SARIF files to {args.sarif_dir}",
                        error_category="transient",
                        is_retryable=True,
                    )
                ),
                file=sys.stderr,
            )

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        result = structured_success(
            data={
                "command": "scan",
                "output_path": str(output_path),
                "findings_count": len(findings),
                "by_severity": config["by_severity"],
                "degraded": config["degraded"],
                "scan_errors": scan_errors,
                "backend": backend_name,
                "coverage": coverage,
                "scan_types": scan_types or (
                    sorted(backend_capabilities) if backend_capabilities else None
                ),
            }
        )
    else:
        result = structured_success(
            data={
                "command": "scan",
                "findings_count": len(findings),
                "by_severity": config["by_severity"],
                "degraded": config["degraded"],
                "scan_errors": scan_errors,
                "backend": backend_name,
                "config": config,
            }
        )

    print(json.dumps(result, ensure_ascii=False))

    # A degraded scan (a scanner fataled / produced no parseable output) is a
    # scan ERROR, not a clean result — fail closed with exit 2 BEFORE the
    # --fail-on threshold so it never reports as exit 0. CI gates on findings.json
    # `degraded` (the scan step is continue-on-error); this exit code is for
    # direct/local callers.
    if scan_errors:
        return 2
    if count_above_threshold(findings, fail_on) > 0:
        return 1
    return 0


if __name__ == "__main__":
    _fix_windows_encoding()
    sys.exit(main())

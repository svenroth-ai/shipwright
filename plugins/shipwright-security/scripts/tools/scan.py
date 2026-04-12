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
) -> dict[str, Any]:
    """Build a shipwright_security_config.json compatible dict."""
    severity_counts = Counter(f.get("severity", "unknown") for f in findings)
    return {
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        "scanner": scanner,
        "total_findings": len(findings),
        "by_severity": {sev: severity_counts.get(sev, 0) for sev in SEVERITY_ORDER},
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

    config = build_config(findings, repo=args.repo, scanner=args.backend)

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
                "backend": args.backend,
                "scan_types": scan_types or sorted(backend.capabilities),
            }
        )
    else:
        result = structured_success(
            data={
                "command": "scan",
                "findings_count": len(findings),
                "by_severity": config["by_severity"],
                "backend": args.backend,
                "config": config,
            }
        )

    print(json.dumps(result, ensure_ascii=False))

    if count_above_threshold(findings, fail_on) > 0:
        return 1
    return 0


if __name__ == "__main__":
    _fix_windows_encoding()
    sys.exit(main())

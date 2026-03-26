#!/usr/bin/env python3
"""Generate a Markdown security report from shipwright_security_config.json.

Reads findings and remediation status, outputs a formatted Markdown report.
Can read from stdin (piped JSON) or from the config file in the project root.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

def _fix_windows_encoding() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
SHARED_ROOT = PLUGIN_ROOT.parent.parent / "shared"

try:
    sys.path.insert(0, str(SHARED_ROOT / "scripts"))
    from lib.errors import structured_error, structured_success  # noqa: E402
except (ImportError, ModuleNotFoundError):
    def structured_error(what_failed, what_was_attempted, error_category, is_retryable,
                         partial_results=None, alternatives=None, context=None):
        return {"success": False, "error": {"what_failed": what_failed}}

    def structured_success(data=None):
        result = {"success": True}
        if data:
            result.update(data)
        return result


def generate_report(findings: list[dict], repo_name: str = "unknown") -> str:
    """Generate a Markdown report from a list of findings."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    severity_counts = Counter(f.get("severity", "unknown") for f in findings)
    status_counts = Counter(f.get("_remediation_status", "open") for f in findings)
    class_counts = Counter(f.get("_remediation_class", "unknown") for f in findings)

    lines = [
        f"# Security Report: {repo_name}",
        f"",
        f"**Generated:** {now}",
        f"**Total Findings:** {len(findings)}",
        f"",
        "## Summary",
        "",
        "### By Severity",
        "",
        "| Severity | Count |",
        "|----------|-------|",
    ]

    for sev in ["critical", "high", "medium", "low", "info"]:
        if sev in severity_counts:
            lines.append(f"| {sev.capitalize()} | {severity_counts[sev]} |")

    lines.extend([
        "",
        "### By Remediation Status",
        "",
        "| Status | Count |",
        "|--------|-------|",
    ])

    for status in ["fixed", "declined", "deferred", "open"]:
        if status in status_counts:
            lines.append(f"| {status.capitalize()} | {status_counts[status]} |")

    lines.extend([
        "",
        "### By Remediation Class",
        "",
        "| Class | Count |",
        "|-------|-------|",
    ])

    for cls in ["auto-fixable", "agent-fixable", "needs-review", "informational"]:
        if cls in class_counts:
            lines.append(f"| {cls} | {class_counts[cls]} |")

    # Detailed findings table
    if findings:
        lines.extend([
            "",
            "## Findings",
            "",
            "| # | Severity | Type | Title | File | Status |",
            "|---|----------|------|-------|------|--------|",
        ])

        for i, f in enumerate(findings, 1):
            sev = f.get("severity", "?")
            ftype = f.get("type", "?")
            title = f.get("rule", f.get("title", "?"))
            afile = f.get("affected_file", f.get("file", "?"))
            status = f.get("_remediation_status", "open")
            lines.append(f"| {i} | {sev} | {ftype} | {title} | {afile} | {status} |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate security report")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument("--repo", default="unknown", help="Repository name for report title")
    args = parser.parse_args()

    # Try reading from stdin first, then from config file
    findings = []
    try:
        if not sys.stdin.isatty():
            data = json.load(sys.stdin)
            findings = data.get("data", data.get("findings", []))
    except (json.JSONDecodeError, Exception):
        pass

    if not findings:
        config_path = Path(args.project_root) / "shipwright_security_config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            findings = config.get("findings", [])

    report = generate_report(findings, args.repo)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        result = structured_success(data={
            "command": "generate_report",
            "output_path": args.output,
            "findings_count": len(findings),
        })
    else:
        result = structured_success(data={
            "command": "generate_report",
            "report_markdown": report,
            "findings_count": len(findings),
        })

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    _fix_windows_encoding()
    sys.exit(main())

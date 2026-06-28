#!/usr/bin/env python3
"""Generate a Markdown security report from shipwright_security_config.json.

Reads findings and remediation status, outputs a formatted Markdown report.
Supports multiple input modes:
  - stdin (piped JSON)
  - --input path (JSON file from scan.py)
  - shipwright_security_config.json in project root (pipeline mode)

Can merge prompt-injection findings via --prompt-risks.

--pr-mode generates a compact report optimized for GitHub PR comments.
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


# SSoT cell escaper (F32): escape every scanner/repo cell so `|`/newline can't break the table.
from markdown_table import escape_cell  # noqa: E402

# ---------------------------------------------------------------------------
# Risk score calculation
# ---------------------------------------------------------------------------

def calculate_risk_level(findings: list[dict[str, Any]]) -> str:
    """Calculate overall risk level from findings.

    CRITICAL: >=1 critical
    HIGH:     >=1 high OR >=5 medium
    MEDIUM:   >=1 medium OR new-dependency finding OR hooks/ change finding
    LOW:      only low/info findings
    NONE:     0 findings
    """
    if not findings:
        return "NONE"

    counts = Counter(f.get("severity", "unknown") for f in findings)

    if counts.get("critical", 0) >= 1:
        return "CRITICAL"
    if counts.get("high", 0) >= 1 or counts.get("medium", 0) >= 5:
        return "HIGH"

    # Detect dependency additions or hooks changes → MEDIUM floor
    has_dep_change = any(
        f.get("rule") == "NEW_DEPENDENCY" for f in findings
    )
    has_hooks_change = any(
        "hooks" in (f.get("affected_file") or "").lower() for f in findings
    )

    if counts.get("medium", 0) >= 1 or has_dep_change or has_hooks_change:
        return "MEDIUM"
    return "LOW"


RISK_EMOJI = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🟢",
    "NONE": "✅",
}


# ---------------------------------------------------------------------------
# Finding loading
# ---------------------------------------------------------------------------

def load_findings_from_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("findings", data.get("data", []))


def load_scan_errors_from_file(path: Path) -> list[dict[str, Any]]:
    """Read the degraded-scan markers (``scan_errors``) from a findings.json.

    Returns [] when the file is absent/invalid or carries no markers — the
    report then renders no degraded banner.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    errors = data.get("scan_errors") if isinstance(data, dict) else None
    return errors if isinstance(errors, list) else []


def load_findings_from_stdin() -> list[dict[str, Any]]:
    try:
        if sys.stdin.isatty():
            return []
        raw = sys.stdin.read()
        if not raw.strip():
            return []
        data = json.loads(raw)
        return data.get("data", data.get("findings", []))
    except (json.JSONDecodeError, Exception):
        return []


# ---------------------------------------------------------------------------
# Per-scanner breakdown
# ---------------------------------------------------------------------------

def scanner_breakdown(findings: list[dict[str, Any]]) -> dict[str, Counter]:
    """Group findings by source scanner with severity counts."""
    buckets: dict[str, Counter] = {}
    for f in findings:
        src = f.get("source", "unknown")
        if src not in buckets:
            buckets[src] = Counter()
        sev = f.get("severity", "unknown")
        buckets[src][sev] += 1
        buckets[src]["total"] += 1
    return buckets


# ---------------------------------------------------------------------------
# Degraded-scan banner (iterate-2026-06-05-scanner-degraded-marker)
# ---------------------------------------------------------------------------

def degraded_banner(scan_errors: list[dict[str, Any]] | None) -> list[str]:
    """Markdown lines warning that one or more scanner legs degraded.

    Returns [] when not degraded so callers can unconditionally splice it in.
    A degraded leg means a scanner was invoked but produced no parseable output
    — the report below is INCOMPLETE and must not read as a clean pass.
    """
    errors = list(scan_errors or [])
    if not errors:
        return []
    lines = [
        "> ⚠️ **Degraded Scan** — one or more scanners failed to produce "
        + "parseable output. Results below are INCOMPLETE; do not read this as a "
        + "clean pass.",
        "",
        "| Scanner | Reason | Detail |",
        "|---------|--------|--------|",
    ]
    for e in errors:
        scanner = str(e.get("scanner", "?"))
        reason = str(e.get("reason", "?"))
        detail = str(e.get("detail", "")).replace("\n", " ").replace("|", "\\|")[:120]
        lines.append(f"| {scanner} | {reason} | {detail} |")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Standard report (existing format)
# ---------------------------------------------------------------------------

def generate_standard_report(
    findings: list[dict[str, Any]],
    repo_name: str = "unknown",
    scan_errors: list[dict[str, Any]] | None = None,
) -> str:
    """Generate the full Markdown report (original format, extended slightly)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    severity_counts = Counter(f.get("severity", "unknown") for f in findings)
    status_counts = Counter(f.get("_remediation_status", "open") for f in findings)
    class_counts = Counter(f.get("_remediation_class", "unknown") for f in findings)
    risk = calculate_risk_level(findings)

    lines = [
        f"# Security Report: {repo_name}",
        "",
        f"**Generated:** {now}",
        f"**Risk Level:** {RISK_EMOJI[risk]} {risk}",
        f"**Total Findings:** {len(findings)}",
        "",
        *degraded_banner(scan_errors),
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

    if findings:
        lines.extend([
            "",
            "## Findings",
            "",
            "| # | Severity | Type | Title | File | Status |",
            "|---|----------|------|-------|------|--------|",
        ])

        for i, f in enumerate(findings, 1):
            sev = escape_cell(f.get("severity", "?"))
            ftype = escape_cell(f.get("type", "?"))
            title = escape_cell(f.get("rule", f.get("title", "?")))
            afile = escape_cell(f.get("affected_file", f.get("file", "?")))
            status = escape_cell(f.get("_remediation_status", "open"))
            lines.append(f"| {i} | {sev} | {ftype} | {title} | {afile} | {status} |")

    lines.append("")
    return "\n".join(lines)


# Backwards-compat alias — existing callers import `generate_report`
generate_report = generate_standard_report


# ---------------------------------------------------------------------------
# PR-mode report (compact for GitHub PR comments)
# ---------------------------------------------------------------------------

PR_COMMENT_MARKER = "<!-- shipwright-security-report -->"


def generate_pr_report(
    findings: list[dict[str, Any]],
    repo_name: str = "unknown",
    scan_errors: list[dict[str, Any]] | None = None,
) -> str:
    """Compact report optimized for a PR comment."""
    risk = calculate_risk_level(findings)
    breakdown = scanner_breakdown(findings)

    lines = [
        PR_COMMENT_MARKER,
        "## 🔒 Shipwright Security Summary",
        "",
        f"**Risk Level:** {RISK_EMOJI[risk]} **{risk}**",
        f"**Total Findings:** {len(findings)}",
        "",
        *degraded_banner(scan_errors),
    ]

    # Scanner breakdown table
    if breakdown:
        lines.extend([
            "| Scanner | Total | Critical | High | Medium | Low |",
            "|---------|------:|---------:|-----:|-------:|----:|",
        ])
        for source in sorted(breakdown.keys()):
            b = breakdown[source]
            lines.append(
                f"| {source} | {b.get('total', 0)} | "
                f"{b.get('critical', 0)} | {b.get('high', 0)} | "
                f"{b.get('medium', 0)} | {b.get('low', 0)} |"
            )
        lines.append("")

    # Findings detail (max 15 to keep PR comment readable)
    if findings:
        # Sort by severity (critical first)
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        sorted_findings = sorted(
            findings,
            key=lambda f: sev_order.get(f.get("severity", "info"), 5),
        )
        displayed = sorted_findings[:15]

        lines.extend([
            "### Findings",
            "",
            "| # | Severity | Rule | File | Description |",
            "|---|----------|------|------|-------------|",
        ])
        for i, f in enumerate(displayed, 1):
            sev = escape_cell(f.get("severity", "?"))
            rule = escape_cell(f.get("rule", "?"))
            afile = escape_cell(f.get("affected_file", "?"))
            line_num = f.get("affected_line")
            afile = f"`{afile}:{line_num}`" if line_num else f"`{afile}`"
            desc = escape_cell((f.get("description", "") or "")[:120])
            if len(f.get("description", "")) > 120:
                desc += "…"
            lines.append(f"| {i} | {sev} | `{rule}` | {afile} | {desc} |")

        if len(sorted_findings) > 15:
            lines.append("")
            lines.append(f"_...and {len(sorted_findings) - 15} more findings (see artifact)._")
        lines.append("")

    # Action required
    lines.append("### Action Required")
    lines.append("")
    if risk == "CRITICAL":
        lines.append("🔴 **Critical findings detected.** This PR should not be merged until resolved.")
    elif risk == "HIGH":
        lines.append("🟠 **High-severity findings detected.** Careful review required.")
    elif risk == "MEDIUM":
        lines.append(
            "🟡 Medium-severity findings or dependency/hooks changes detected. "
            "Standard review with extra attention to the flagged items."
        )
    elif risk == "LOW":
        lines.append("🟢 Only low-severity findings. Standard review sufficient.")
    else:
        lines.append("✅ No security findings. Standard review sufficient.")

    lines.append("")
    lines.append(
        "_Powered by [shipwright-security](plugins/shipwright-security/) — "
        "Semgrep, Trivy, Gitleaks, and Shipwright Prompt Injection Scanner._"
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AC-1 of iterate-2026-05-14-triage-producers-2: triage emission
# ---------------------------------------------------------------------------

_SECURITY_KIND_FROM_SEVERITY = {
    "critical": "bug",
    "high": "bug",
    "medium": "improvement",
    "low": "improvement",
    "info": "improvement",
}

_KNOWN_SEVERITIES = ("critical", "high", "medium", "low", "info")


def _emit_findings_to_triage(
    project_root: Path,
    findings: list[dict[str, Any]],
    *,
    run_id: str | None = None,
    commit: str | None = None,
) -> int:
    """Append security findings to ``.shipwright/triage.jsonl`` (best-effort).

    One triage item per finding. ``source="security"``, severity inherited
    verbatim from the scanner (unrecognized → fallback to ``"medium"``).
    ``dedup_key=f"{tool}:{check_id}:{file}:{line}"`` makes the same finding
    on the same line stable across runs; ``match_commit=True`` with a 24h
    window lets the finding re-fire daily until promoted/dismissed.

    Returns the number of NEW items appended (duplicates are skipped). Any
    per-finding error is logged to stderr and swallowed — emission never
    blocks the consolidation path.
    """
    if not findings:
        return 0

    # Lazy import: avoid forcing shared/scripts/ onto sys.path at module
    # import time. Plugin tests run with a constrained path.
    try:
        shared_scripts = (
            Path(__file__).resolve().parents[4] / "shared" / "scripts"
        )
        if str(shared_scripts) not in sys.path:
            sys.path.insert(0, str(shared_scripts))
        from triage import append_triage_item_idempotent  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[security] triage import failed: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return 0

    appended = 0
    for f in findings:
        try:
            if not isinstance(f, dict):
                continue
            tool = str(f.get("source") or "unknown")
            check_id = str(f.get("rule") or f.get("type") or "unknown")
            affected_file = str(f.get("affected_file") or f.get("file") or "unknown")
            line_val = f.get("affected_line") or f.get("line") or "?"
            description = str(f.get("description") or "")

            if not check_id or check_id == "unknown" or affected_file == "unknown":
                # Producer cannot build a stable dedup key from this finding
                # — best-effort skip + stderr (rather than emit a useless
                # "unknown:unknown:..." key that pollutes the inbox).
                sys.stderr.write(
                    f"[security] skipping finding missing rule/file: "
                    f"{f!r}\n"
                )
                continue

            raw_sev = str(f.get("severity") or "").lower()
            if raw_sev not in _KNOWN_SEVERITIES:
                # Conservative fallback — never raise into the consolidation
                # path (which would break the entire report). "medium" is
                # the operator-useful default.
                severity = "medium"
            else:
                severity = raw_sev

            kind = _SECURITY_KIND_FROM_SEVERITY[severity]

            summary = description.replace("\n", " ").strip()[:80]
            title = f"[{tool}] {check_id}: {summary}" if summary else \
                    f"[{tool}] {check_id}"
            title = title[:160]

            detail_parts = [f"{affected_file}:{line_val}"]
            if description:
                detail_parts.append(description)
            suggested_fix = f.get("suggested_fix") or f.get("remediation")
            if suggested_fix:
                detail_parts.append(f"fix: {suggested_fix}")
            detail = " | ".join(detail_parts)

            evidence_path = f.get("_evidence_path") or f.get("evidence_path")

            new_id = append_triage_item_idempotent(
                project_root,
                source="security",
                severity=severity,
                kind=kind,
                title=title,
                detail=detail,
                dedup_key=f"{tool}:{check_id}:{affected_file}:{line_val}",
                evidence_path=str(evidence_path) if evidence_path else None,
                run_id=run_id,
                commit=commit,
                match_commit=True,
                window_seconds=24 * 3600,
            )
            if new_id is not None:
                appended += 1
        except Exception as exc:  # noqa: BLE001 — best-effort per-finding
            sys.stderr.write(
                f"[security] triage emit failed for finding "
                f"{f.get('rule', '<no-rule>') if isinstance(f, dict) else '<non-dict>'}: "
                f"{type(exc).__name__}: {exc}\n"
            )
    return appended


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# Schema version for the machine-readable JSON sidecar emitted via
# --json-output. Bump if you change top-level fields. Existing top-level
# fields stay stable; new fields may be added.
JSON_SIDECAR_SCHEMA_VERSION = 1


def build_json_sidecar(
    findings: list[dict[str, Any]],
    repo_name: str = "unknown",
    scan_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compose the machine-readable sidecar payload.

    Mirrors the data presented in generate_standard_report so an
    automated consumer (CI, /shipwright-iterate handoff) can read this
    file instead of parsing the markdown.
    """
    errors = list(scan_errors or [])
    by_severity = Counter(f.get("severity", "unknown") for f in findings)
    breakdown = scanner_breakdown(findings)
    by_source = {src: int(cnt.get("total", 0)) for src, cnt in breakdown.items()}
    return {
        "schema_version": JSON_SIDECAR_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": repo_name,
        "risk_level": calculate_risk_level(findings),
        "total_findings": len(findings),
        "by_severity": dict(by_severity),
        "by_source": by_source,
        "degraded": bool(errors),
        "scan_errors": errors,
        "findings": list(findings),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate security report")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--input", help="Input JSON file (e.g. findings.json from scan.py)")
    parser.add_argument("--prompt-risks", help="Additional JSON file with prompt-injection findings")
    parser.add_argument("--output", help="Output file path")
    parser.add_argument(
        "--json-output",
        help="Optional machine-readable sidecar path (e.g. .shipwright/securityreports/latest.json)",
    )
    parser.add_argument("--repo", default="unknown", help="Repository name for report title")
    parser.add_argument(
        "--pr-mode",
        action="store_true",
        help="Generate compact PR-comment-friendly report",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    args = parser.parse_args()

    # Load findings
    findings: list[dict[str, Any]] = []

    # Priority 1: --input
    if args.input:
        findings = load_findings_from_file(Path(args.input))

    # Priority 2: stdin
    if not findings:
        findings = load_findings_from_stdin()

    # Priority 3: shipwright_security_config.json
    config_path = Path(args.project_root) / "shipwright_security_config.json"
    if not findings:
        findings = load_findings_from_file(config_path)

    # Degraded-scan markers — read from the same source the findings came from
    # (the scan.py findings.json carries `scan_errors`). The findings list and
    # the degraded flag are independent: a degraded leg can have 0 findings.
    scan_errors: list[dict[str, Any]] = []
    if args.input:
        scan_errors = load_scan_errors_from_file(Path(args.input))
    if not scan_errors:
        scan_errors = load_scan_errors_from_file(config_path)

    # Merge prompt-injection findings if provided
    if args.prompt_risks:
        prompt_findings = load_findings_from_file(Path(args.prompt_risks))
        findings = list(findings) + list(prompt_findings)

    # Iterate-2 AC-1: mirror findings into .shipwright/triage.jsonl before
    # report rendering. Best-effort — emission failures never block the
    # report.
    try:
        _emit_findings_to_triage(Path(args.project_root), findings)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[security] triage emission top-level failed: "
            f"{type(exc).__name__}: {exc}\n"
        )

    # Generate report
    if args.pr_mode:
        report = generate_pr_report(findings, args.repo, scan_errors)
    else:
        report = generate_standard_report(findings, args.repo, scan_errors)

    risk_level = calculate_risk_level(findings)

    # Optional machine-readable sidecar (independent of --output / --format).
    if args.json_output:
        sidecar = build_json_sidecar(findings, args.repo, scan_errors)
        sidecar_path = Path(args.json_output)
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if args.format == "json":
        result = structured_success(data={
            "command": "generate_report",
            "findings_count": len(findings),
            "risk_level": risk_level,
            "report_markdown": report,
            "json_sidecar_path": args.json_output,
        })
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report, encoding="utf-8")
        result = structured_success(data={
            "command": "generate_report",
            "output_path": args.output,
            "json_sidecar_path": args.json_output,
            "findings_count": len(findings),
            "risk_level": risk_level,
        })
    else:
        result = structured_success(data={
            "command": "generate_report",
            "report_markdown": report,
            "json_sidecar_path": args.json_output,
            "findings_count": len(findings),
            "risk_level": risk_level,
        })

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    _fix_windows_encoding()
    sys.exit(main())

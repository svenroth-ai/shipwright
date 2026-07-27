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

# Plugin-local libs (coverage manifest + rendering + triage emission).
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
from coverage_report import coverage_banner, coverage_table  # noqa: E402
from scan_coverage import with_prompt_injection_row  # noqa: E402

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
    """Findings from a scan artifact, or [] when it cannot be read.

    The non-dict guard matters: a JSON array (a hand-written or
    wrong-tool ``--prompt-risks`` / ``--input`` file) used to reach
    ``data.get`` and crash the whole report with an AttributeError. Every other
    loader here degrades to [] instead of taking the report down with it, and a
    file we could not read must not be mistaken for a scanned-clean one either —
    ``_prompt_risks_readable`` is what decides the coverage claim.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    findings = data.get("findings", data.get("data", []))
    return findings if isinstance(findings, list) else []


def _load_list_key(path: Path, key: str) -> list[dict[str, Any]]:
    """Read a top-level list field from a findings.json / sidecar.

    Returns [] when the file is absent, unparseable, or carries no such field.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, list) else []


def load_scan_errors_from_file(path: Path) -> list[dict[str, Any]]:
    """Degraded-scan markers (``scan_errors``); [] renders no degraded banner."""
    return _load_list_key(path, "scan_errors")


def _prompt_risks_readable(path: Path) -> bool:
    """True only when a prompt-risks file exists AND parses to the expected shape.

    A missing or malformed file must NOT let the prompt-injection coverage row
    claim `covered` — that is the same false-clean signal the manifest exists to
    remove, just one level up.
    """
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(payload, dict):
        return False
    return isinstance(payload.get("findings"), list) or isinstance(
        payload.get("data"), list)


def load_coverage_from_file(path: Path) -> list[dict[str, Any]]:
    """Coverage manifest (``coverage``) — what the scan actually looked at.

    [] means the producer did not report coverage (a pre-manifest scan), which
    the report renders as "Coverage not reported" rather than a clean sweep.
    """
    return _load_list_key(path, "coverage")


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
    coverage: list[dict[str, Any]] | None = None,
) -> str:
    """Generate the full Markdown report (original format, extended slightly).

    ``coverage`` is the scan coverage manifest — what this run looked at and,
    crucially, what it did NOT. It renders as a banner above the findings plus
    a per-class table, so a report produced on a machine with one scanner
    installed cannot read as clean for every class.
    """
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
        *coverage_banner(coverage),
        *degraded_banner(scan_errors),
        *coverage_table(coverage),
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
    coverage: list[dict[str, Any]] | None = None,
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
        *coverage_banner(coverage),
        *degraded_banner(scan_errors),
        # The full manifest, not just the banner: a PR reader has to be able to
        # see WHICH classes were covered, degraded or skipped, otherwise the
        # compact report re-creates the "reads clean everywhere" problem in the
        # one place most people actually look.
        *coverage_table(coverage),
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
# Triage emission (iterate-2026-05-14-triage-producers-2 AC-1; the collapsed
# scan card is AC-6 of iterate-2026-07-27-security-coverage-manifest). Both
# live in scripts/lib/security_triage_emit.py; re-exported here because this
# module is the historical import site.
# ---------------------------------------------------------------------------

from security_triage_emit import emit_scan_card  # noqa: E402
from security_triage_emit import (  # noqa: E402
    emit_findings_to_triage as _emit_findings_to_triage,
)


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
    coverage: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compose the machine-readable sidecar payload.

    Mirrors the data presented in generate_standard_report so an
    automated consumer (CI, /shipwright-iterate handoff) can read this
    file instead of parsing the markdown.

    ``coverage`` is additive, so ``schema_version`` stays 1 per this payload's
    own contract ("existing top-level fields stay stable; new fields may be
    added"). ``scan_compare`` reads it to decide which classes two runs may be
    compared over.
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
        "coverage": list(coverage or []),
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

    # Coverage manifest — what the scan looked at. When --input is supplied its
    # manifest is AUTHORITATIVE, absence included: falling back to the local
    # config would attach another scan's coverage to these findings, and a
    # pre-feature input must render "coverage not reported" rather than inherit
    # a stale claim. Read before the prompt-injection merge so the merge can add
    # its own row.
    coverage = (
        load_coverage_from_file(Path(args.input)) if args.input
        else load_coverage_from_file(config_path)
    )

    # Merge prompt-injection findings if provided. `ran` must mean "output was
    # read", not "a flag was passed": load_findings_from_file returns [] for a
    # missing/unparseable file, so keying the row off the flag alone would claim
    # the class was checked when nothing was.
    prompt_scan_read = False
    if args.prompt_risks:
        prompt_scan_read = _prompt_risks_readable(Path(args.prompt_risks))
        findings = list(findings) + list(
            load_findings_from_file(Path(args.prompt_risks)))
    # The prompt-injection scan is a class of its own. Omitting it entirely
    # reads as clean, so it gets a row either way.
    coverage = with_prompt_injection_row(coverage, ran=prompt_scan_read)

    # Iterate-2 AC-1: mirror findings into .shipwright/triage.jsonl before
    # report rendering, plus the collapsed scan card carrying the severity
    # split and the scope question. Best-effort — emission failures never
    # block the report.
    try:
        _emit_findings_to_triage(Path(args.project_root), findings)
        emit_scan_card(
            Path(args.project_root), findings,
            coverage=coverage, repo=args.repo, report_path=args.output,
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[security] triage emission top-level failed: "
            f"{type(exc).__name__}: {exc}\n"
        )

    # Generate report
    if args.pr_mode:
        report = generate_pr_report(findings, args.repo, scan_errors, coverage)
    else:
        report = generate_standard_report(findings, args.repo, scan_errors, coverage)

    risk_level = calculate_risk_level(findings)

    # Optional machine-readable sidecar (independent of --output / --format).
    if args.json_output:
        sidecar = build_json_sidecar(findings, args.repo, scan_errors, coverage)
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

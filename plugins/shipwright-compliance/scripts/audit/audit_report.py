"""Audit-report rendering (plan v7 Option Z, Step 9).

Takes an :class:`AuditReport` and produces:

1. A Markdown summary (``compliance/audit-report.md``) split into two
   top-level sections:
   - **Preventive re-checks** (source=preventive-rerun): Groups C/F/B3/B6
   - **Detective-only checks** (source=detective-only): everything else
2. A JSON payload (``shipwright_audit_report.json``) with each finding's
   ``source`` field preserved.

Rendering is pure / side-effect-free except for the ``write`` helper,
which commits both artifacts to disk.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from scripts.audit.audit_adapters import (
    SOURCE_DETECTIVE_ONLY,
    SOURCE_PREVENTIVE_RERUN,
    Finding,
)
from scripts.audit.audit_detector import AuditReport

_SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_STATUS_ORDER = {"fail": 0, "skip": 1, "pass": 2}


def _sort_key(f: Finding) -> tuple:
    """Stable ordering: fails first, then by group letter, then severity."""
    return (
        _STATUS_ORDER.get(f.status, 99),
        f.group,
        _SEVERITY_ORDER.get(f.severity, 99),
        f.check_id,
    )


def _render_summary_table(findings: list[Finding]) -> list[str]:
    """One-row-per-group rollup."""
    if not findings:
        return ["_(no findings collected)_", ""]

    by_group: dict[str, dict[str, int]] = {}
    for f in findings:
        bucket = by_group.setdefault(f.group, {"fail": 0, "pass": 0, "skip": 0})
        bucket[f.status] = bucket.get(f.status, 0) + 1

    lines = [
        "| Group | Fail | Skip | Pass |",
        "| ----- | ---: | ---: | ---: |",
    ]
    for group in sorted(by_group):
        b = by_group[group]
        lines.append(f"| {group} | {b.get('fail', 0)} | {b.get('skip', 0)} | {b.get('pass', 0)} |")
    lines.append("")
    return lines


def _render_findings_block(title: str, items: list[Finding]) -> list[str]:
    if not items:
        return [f"### {title}", "", "_(none)_", ""]

    lines = [f"### {title}", ""]
    for f in sorted(items, key=_sort_key):
        status_marker = {"fail": "❌", "skip": "⏭", "pass": "✅"}.get(f.status, "•")
        lines.append(
            f"- {status_marker} **{f.check_id}** ({f.group}, {f.severity}): "
            f"{f.name}"
        )
        if f.detail:
            lines.append(f"  - {f.detail}")
        if f.suggested_iterate_cmd:
            lines.append(f"  - _Suggested:_ `{f.suggested_iterate_cmd}`")
    lines.append("")
    return lines


def render_markdown(
    report: AuditReport,
    *,
    project_root: Path | None = None,
) -> str:
    """Produce the Markdown form of the report."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    preventive = [f for f in report.findings if f.source == SOURCE_PREVENTIVE_RERUN]
    detective = [f for f in report.findings if f.source == SOURCE_DETECTIVE_ONLY]

    lines: list[str] = [
        "# Shipwright Detective Audit",
        "",
        f"Generated: {generated}",
    ]
    if project_root is not None:
        lines.append(f"Project: `{project_root.as_posix()}`")
    lines.extend([
        "",
        "> Cross-artifact consistency scan (plan v7). Surfaces drift classes that",
        "> live between the preventive Canon gate and the reactive Phase-Quality",
        "> Stop hook. See `docs/guide.md` § 4.10 for the 3-layer positioning.",
        "",
        "## Summary",
        "",
    ])
    lines.extend(_render_summary_table(report.findings))

    if report.import_gate_error:
        lines.extend([
            "## Import Gate Error",
            "",
            "The audit aborted before any group ran because a required",
            "iterate-12 verifier symbol has drifted:",
            "",
            "```",
            report.import_gate_error,
            "```",
            "",
        ])

    if report.groups_skipped:
        lines.append("## Groups Skipped")
        lines.append("")
        for group, reason in sorted(report.groups_skipped):
            lines.append(f"- **{group}** — {reason}")
        lines.append("")

    lines.append("## Findings")
    lines.append("")
    lines.extend(_render_findings_block(
        "Preventive re-checks (iterate-12 verifiers, re-run on demand)",
        preventive,
    ))
    lines.extend(_render_findings_block(
        "Detective-only checks (drift classes Phase-Quality can't see)",
        detective,
    ))

    if report.fixes_applied:
        lines.append("## Fixes Applied")
        lines.append("")
        for p in report.fixes_applied:
            lines.append(f"- {p}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_json(report: AuditReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"


def write(
    report: AuditReport,
    project_root: Path,
    *,
    markdown: bool = True,
    json_out: bool = True,
) -> dict[str, Path]:
    """Persist the report(s) under ``project_root``. Returns {format: path}."""
    paths: dict[str, Path] = {}
    if markdown:
        md_dir = project_root / "compliance"
        md_dir.mkdir(exist_ok=True)
        md_path = md_dir / "audit-report.md"
        md_path.write_text(render_markdown(report, project_root=project_root),
                           encoding="utf-8")
        paths["md"] = md_path
    if json_out:
        json_path = project_root / "shipwright_audit_report.json"
        json_path.write_text(render_json(report), encoding="utf-8")
        paths["json"] = json_path
    return paths

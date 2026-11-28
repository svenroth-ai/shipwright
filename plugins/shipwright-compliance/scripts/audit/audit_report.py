"""Audit-report rendering (plan v7 Option Z, Step 9).

Takes an :class:`AuditReport` and produces:

1. A Markdown summary (``.shipwright/compliance/audit-report.md``) split into two
   top-level sections:
   - **Preventive re-checks** (source=preventive-rerun): Groups C/F/B3/B6
   - **Detective-only checks** (source=detective-only): everything else
2. A JSON payload (``.shipwright/compliance/audit-report.json``) with each
   finding's ``source`` field preserved. (Relocated from the repo root in
   iterate-2026-06-09 so the gitignore canon covers it; stdout stays the
   stable contract for automated callers.)

Rendering is pure / side-effect-free except for the ``write`` helper,
which commits both artifacts to disk.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.audit.audit_adapters import (
    SOURCE_DETECTIVE_ONLY,
    SOURCE_PREVENTIVE_RERUN,
    Finding,
)
from scripts.audit.audit_detector import AuditReport
from scripts.lib.audit_freshness import mark_audit_report_stale

_SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_STATUS_ORDER = {"fail": 0, "skip": 1, "pass": 2}


def format_generated(ran_at: str | None) -> str:
    """The ``Generated:`` stamp, derived from the run record (``report.ran_at``).

    The run record is the one source for "last run"; the wall clock is only the
    fallback for a hand-built report that never recorded one.
    """
    when = None
    if ran_at:
        try:
            when = datetime.fromisoformat(ran_at)
        except ValueError:
            when = None
    if when is None:
        when = datetime.now(timezone.utc)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


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
        advisory = f.status == "pass" and f.detail.startswith("advisory")
        status_marker = (
            "⚠️" if advisory
            else {"fail": "❌", "skip": "⏭", "pass": "✅"}.get(f.status, "•")
        )
        lines.append(
            f"- {status_marker} **{f.check_id}** ({f.group}, {f.severity}): "
            f"{f.name}"
        )
        if f.detail:
            lines.append(f"  - {f.detail}")
        # Only a real FAIL or an explicit advisory flag (FR-01.10/AC06: reported
        # WITH a fix, without failing) warrants a remediation command. A plain
        # passing/skipped check is not a problem, so emitting "Suggested:
        # …reconcile" on it is a false action (alarm-fatigue).
        if f.suggested_iterate_cmd and (f.status == "fail" or advisory):
            lines.append(f"  - _Suggested:_ `{f.suggested_iterate_cmd}`")
    lines.append("")
    return lines


def render_markdown(
    report: AuditReport,
    *,
    project_root: Path | None = None,
) -> str:
    """Produce the Markdown form of the report."""
    generated = format_generated(report.ran_at)
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
    if not report.ran_at:
        # Mint once so the md and json can never disagree about when this ran.
        report.ran_at = datetime.now(timezone.utc).isoformat()
    paths: dict[str, Path] = {}
    if markdown:
        md_dir = project_root / ".shipwright" / "compliance"
        md_dir.mkdir(parents=True, exist_ok=True)
        md_path = md_dir / "audit-report.md"
        md_path.write_text(render_markdown(report, project_root=project_root),
                           encoding="utf-8")
        paths["md"] = md_path
    if json_out:
        # Under .shipwright/compliance/ (NOT repo root) since iterate-2026-06-09:
        # a transient detective artifact (regenerated each run, not in
        # audit_staleness.DOC_REGISTRY) belongs on a gitignored path so it never
        # leaks as `??`. Living under .shipwright/ lets the .shipwright/-scoped
        # gitignore canon re-exclude it, propagating the ignore to adopted repos.
        # The stdout JSON payload remains the stable contract for automated callers.
        json_dir = project_root / ".shipwright" / "compliance"
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / "audit-report.json"
        json_path.write_text(render_json(report), encoding="utf-8")
        paths["json"] = json_path
        if not markdown:
            # An older md left behind must say so, not pose as the current run.
            mark_audit_report_stale(project_root)
    return paths

"""Aggregate Markdown renderers — skill-compliance dashboards + report.

Three artifacts — all TRANSIENT derived caches written UNDER the gitignored
``FINDING_DIR`` (``.shipwright/compliance/skill-compliance/``) so idle main
stays clean (iterate-2026-06-09; ADR-089 split for this producer):

* :func:`rewrite_aggregated_report` — full ``{FINDING_DIR}/_report.md``
  (last ``MAX_REPORT_RUNS`` runs, per-category detail).
* :func:`rewrite_session_findings_summary` — short-form
  ``{FINDING_DIR}/_findings.md`` digest consumed by the
  SessionStart-Injection hook (``capture_session_id``).
* :func:`write_quality_dashboard_file` — per-phase matrix
  ``{FINDING_DIR}/_dashboard.md`` (newest finding per phase).

The project-wide Compliance Dashboard's bloat-findings column lives
in :mod:`._bloat_findings` (so this module stays focused on Markdown
rendering only).

Iterate Campaign B (B3): split out of the 1108-LOC monolith so
``_aggregates.py`` stays under the 300-LOC budget.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._aggregates import (
    LoadedFinding,
    _roll_up_counts,
    count_by_status,
    load_findings,
)
from ._constants import (
    CATEGORIES,
    DASHBOARD_PATH,
    MAX_REPORT_RUNS,
    MAX_SESSION_SUMMARY_RUNS,
    REPORT_PATH,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    SUMMARY_PATH,
)
from ._findings import now_iso


def rewrite_aggregated_report(project_root: Path) -> Path | None:
    """Regenerate the transient ``{FINDING_DIR}/_report.md`` roll-up."""
    findings = load_findings(project_root)[:MAX_REPORT_RUNS]
    path = project_root / REPORT_PATH
    if not findings:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Skill Compliance Report\n\n_No audits recorded yet._\n",
            encoding="utf-8",
        )
        return path

    lines = [
        "# Skill Compliance Report",
        "",
        f"_Regenerated {now_iso()} from last {len(findings)} run(s)._",
        "",
        "| Phase | Run | Audited | Source | PASS | FAIL | WARN | SKIP |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for f in findings:
        counts = _roll_up_counts(f.payload)
        lines.append(
            f"| {f.phase} | `{f.run_id}` | {f.audited_at} | {f.source} | "
            f"{counts[STATUS_PASS]} | {counts[STATUS_FAIL]} | "
            f"{counts[STATUS_WARN]} | {counts[STATUS_SKIP]} |"
        )
    lines.append("")
    for f in findings:
        lines.extend(_render_run_detail(f))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _render_run_detail(f: LoadedFinding) -> list[str]:
    lines: list[str] = [f"## {f.phase} — {f.run_id} ({f.audited_at})", ""]
    any_emitted = False
    for category in CATEGORIES:
        items = f.payload.get(category, [])
        if not items:
            continue
        any_emitted = True
        lines.append(f"### {category}")
        for item in items:
            status = item.get("status", "?")
            check_id = item.get("id", "?")
            evidence = item.get("evidence", "")
            tier = item.get("tier")
            tier_suffix = " _(tier-2)_" if tier == 2 else ""
            lines.append(f"- **{check_id}** — {status}{tier_suffix}: {evidence}")
        lines.append("")
    if not any_emitted:
        lines.append("_No checks recorded for this run._")
        lines.append("")
    return lines


def rewrite_session_findings_summary(project_root: Path) -> Path | None:
    """Regenerate the transient ``{FINDING_DIR}/_findings.md`` digest."""
    findings = load_findings(project_root)[:MAX_SESSION_SUMMARY_RUNS]
    path = project_root / SUMMARY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not findings:
        path.write_text(
            "# Skill Compliance — Recent Findings\n\n_No audits recorded yet._\n",
            encoding="utf-8",
        )
        return path

    lines = [
        "# Skill Compliance — Recent Findings",
        "",
        f"_Regenerated {now_iso()} from last {len(findings)} run(s)._",
        "",
    ]
    for f in findings:
        counts = _roll_up_counts(f.payload)
        lines.append(f"## {f.phase} — {f.run_id}")
        lines.append(f"- audited_at: {f.audited_at}")
        lines.append(f"- source: {f.source}")
        lines.append(
            f"- totals: {counts[STATUS_PASS]} PASS · "
            f"{counts[STATUS_FAIL]} FAIL · {counts[STATUS_WARN]} WARN · "
            f"{counts[STATUS_SKIP]} SKIP"
        )
        fails: list[dict[str, Any]] = []
        for category in CATEGORIES:
            for item in f.payload.get(category, []):
                if item.get("status") == STATUS_FAIL and item.get("tier") != 2:
                    fails.append(item)
        if fails:
            lines.append("- open FAILs:")
            for item in fails[:5]:
                lines.append(
                    f"  - **{item.get('id','?')}** {item.get('evidence','')}"
                )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_quality_dashboard_file(project_root: Path) -> Path | None:
    """Regenerate the transient ``{FINDING_DIR}/_dashboard.md`` roll-up.

    Table: one row per phase, one column per category. Newest finding per
    phase wins. Heuristic (Tier-2) checks are reported as a separate
    count so reviewers can ignore low-signal noise (plan § 3).
    """
    all_findings = load_findings(project_root)
    latest_per_phase: dict[str, LoadedFinding] = {}
    for f in all_findings:
        latest_per_phase.setdefault(f.phase, f)

    path = project_root / DASHBOARD_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not latest_per_phase:
        path.write_text(
            "# Skill Compliance Dashboard\n\n_No audits recorded yet._\n",
            encoding="utf-8",
        )
        return path

    lines = [
        "# Skill Compliance Dashboard",
        "",
        f"_Regenerated {now_iso()}. Newest finding per phase._",
        "",
        "| Phase | Audited | Run | canon | workflow | infra | trace | quality | spec | Tier-2 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for phase in sorted(latest_per_phase):
        f = latest_per_phase[phase]
        cells: list[str] = []
        tier2_total = 0
        for category in CATEGORIES:
            items = f.payload.get(category, [])
            if not items:
                cells.append("—")
                continue
            counts = count_by_status(items)
            tier2_total += sum(1 for it in items if it.get("tier") == 2)
            cells.append(
                f"{counts[STATUS_PASS]}P/{counts[STATUS_FAIL]}F"
                + (f"/{counts[STATUS_WARN]}W" if counts[STATUS_WARN] else "")
            )
        lines.append(
            f"| {phase} | {f.audited_at} | `{f.run_id}` | "
            + " | ".join(cells)
            + f" | {tier2_total} |"
        )
    lines.append("")
    lines.append(
        "_Legend: `NP/NF[/NW]` = PASS / FAIL / WARN counts per category._ "
        "_Tier-2 column counts heuristic (low-signal) checks; never triggers enforcement._"
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


__all__ = [
    "rewrite_aggregated_report",
    "rewrite_session_findings_summary",
    "write_quality_dashboard_file",
]

"""Dashboard rendering for the Control Verdict + inline Consistency Audit.

Keeps ``compliance_report.py`` at its grandfathered ceiling (anti-ratchet):
the Shipwright→``GradeInputs`` adapter, the Control Verdict block (AR-01) and
the inline Consistency Audit summary (AR-03) all live here. The scorer itself
(``control_grade.py``) stays repo-agnostic; this module is the only
Shipwright-specific glue.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.lib._latest_suite import resolve_latest_full_suite
from scripts.lib.control_grade import GradeInputs, GradeReport, compute_grade

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData

_COPYLEFT = ("GPL", "AGPL", "LGPL", "MPL")
_UNKNOWN_LICENSES = {"unknown", "-", "", "none"}
_STATUS_MARK = {"ok": "✅", "gap": "⚠️", "n/a": "n/a"}


def _ratchet_delta(project_root: Path) -> int | None:
    """Net bloat ratchet delta, or None when no baseline (lazy import —
    mirrors ``_bloat_dashboard_rows`` to avoid shadowing plugin-local lib)."""
    import sys
    # Ensure shared/scripts is importable regardless of whether
    # compliance_report (which also sets this up) was imported first.
    shared = Path(__file__).resolve().parents[4] / "shared" / "scripts"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    try:
        from lib.phase_quality import collect_bloat_summary
    except ImportError:  # pragma: no cover - broken env only
        return None
    try:
        return int(collect_bloat_summary(project_root)["ratchet_delta"])
    except Exception:  # noqa: BLE001  # pragma: no cover - tolerant
        return None


def build_grade_inputs(data: ComplianceData) -> GradeInputs:
    """Map this project's ``ComplianceData`` onto the repo-agnostic inputs."""
    events = data.work_events
    fr_ids_in_events: set[str] = set()
    for we in events:
        fr_ids_in_events.update(we.affected_frs)
    covered = sum(
        1 for r in data.requirements
        if r.id in fr_ids_in_events or r.sections
    )
    suite = resolve_latest_full_suite(events)

    deps = data.dependencies
    unknown = sum(
        1 for d in deps if (d.license or "").strip().lower() in _UNKNOWN_LICENSES)
    copyleft = sum(
        1 for d in deps
        if any(cl in (d.license or "").upper() for cl in _COPYLEFT))

    if events:
        span = f"{events[0].timestamp[:10]} → {events[-1].timestamp[:10]}"
        verified = f"shipwright_events.jsonl ({len(events)} events, {span})"
    else:
        verified = "shipwright_events.jsonl (no events)"

    return GradeInputs(
        frs_total=len(data.requirements),
        frs_covered=covered,
        events_total=len(events),
        events_fr_tagged=sum(1 for we in events if we.affected_frs),
        latest_full_suite_passed=suite.passed if suite else None,
        latest_full_suite_total=suite.total if suite else None,
        latest_full_suite_date=suite.date if suite else "",
        # provenance = linked to an ADR, a commit, or a recorded test run.
        events_with_provenance=sum(
            1 for we in events if we.adr_id or we.commit or we.tests_total > 0),
        # Reconciliation needs per-change behavior-impact (BP-2); not yet on
        # the event wire-format, so n/a here. Flip when WorkEvent gains it.
        reconciliation_measurable=False,
        # Security: the local report is stale/FP-laden; the authoritative
        # posture is the CI gate (AR-10 ingest). n/a until then — never a
        # false CRITICAL.
        security_measurable=False,
        bloat_ratchet_delta=_ratchet_delta(data.project_root),
        deps_total=len(deps),
        deps_unknown_license=unknown,
        deps_copyleft=copyleft,
        verified_from=verified,
    )


def latest_tests_row(work_events) -> str:
    """The 'All unit tests passing' Quality-Indicators row (AR-02).

    Reads the latest *full* suite (not the last event), so a trailing run
    of doc/tooling changes can never surface a ``0/0`` headline when the log
    holds a real suite. Keeps ``0/0 WARN`` only when no suite ever ran."""
    suite = resolve_latest_full_suite(work_events)
    if suite is None:
        return (
            "| All unit tests passing | 0/0 | WARN | "
            "no test events recorded yet |"
        )
    ok = suite.passed == suite.total
    badge = "PASS" if ok else "WARN"
    why = ""
    if not ok:
        why = (
            f"{suite.total - suite.passed}/{suite.total} not green in last "
            "full suite — see test-evidence.md"
        )
    if suite.changes_since:
        sep = "; " if why else ""
        why += f"{sep}+{suite.changes_since} change(s) since last full suite"
    return f"| All unit tests passing | {suite.passed}/{suite.total} | {badge} | {why} |"


def _verdict_emoji(report: GradeReport) -> str:
    if not report.gradeable:
        return "❔"
    return {"A": "✅", "B": "✅", "C": "⚠️", "D": "⚠️", "F": "❌"}.get(
        report.grade, "⚠️")


def render_control_block(data: ComplianceData) -> list[str]:
    """The Control Verdict + Control Grade block (AR-01), rendered atop the
    dashboard's Quality Indicators."""
    return format_control_block(compute_grade(build_grade_inputs(data)))


def format_control_block(report: GradeReport) -> list[str]:
    """Render a computed grade to markdown (split from compute so the
    band/display agreement is unit-testable with a synthetic report)."""
    lines = [
        f"## {_verdict_emoji(report)} Control Verdict",
        "",
        f"> **{report.verdict}**",
        "",
    ]
    if report.gradeable:
        # Display the FLOORED integer: band thresholds are integers, so
        # int(score) is always on the same side of every threshold as the
        # assigned letter — the shown number can never contradict the grade
        # (a `:.0f` round could show 90/100 next to a 'B'). Cert-critical.
        lines.append(
            f"### Control Grade: **{report.grade}** "
            f"({int(report.score)}/100) — {report.band_label}"
        )
    else:
        lines.append("### Control Grade: **Not gradeable**")
    lines.extend([
        "",
        "| | Dimension | Signal | Anchor |",
        "|---|-----------|--------|--------|",
    ])
    for d in report.dimensions:
        mark = _STATUS_MARK.get(d.status, d.status)
        lines.append(f"| {mark} | {d.label} | {d.detail} | {d.anchor} |")
    lines.extend([
        "",
        f"Verified from: `{report.verified_from}`",
        "",
        "_Grade = importance-weighted average over the measurable dimensions "
        "(n/a excluded from the denominator), in Anlehnung an OpenSSF "
        "Scorecard. Age is neutral; only unreconciled change and net growth "
        "are control failures._",
        "",
    ])
    return lines


def _audit_generated_date(project_root: Path) -> str:
    """Parse the 'Generated:' date from audit-report.md (deterministic;
    the JSON payload carries no timestamp)."""
    md = project_root / ".shipwright" / "compliance" / "audit-report.md"
    if not md.exists():
        return ""
    try:
        for line in md.read_text(encoding="utf-8").splitlines():
            if line.startswith("Generated:"):
                return line.split("Generated:", 1)[1].strip()[:10]
    except OSError:  # pragma: no cover - tolerant
        pass
    return ""


def render_consistency_audit(project_root: Path) -> list[str]:
    """Inline Consistency Audit summary (AR-03) — replaces the dead
    gitignored ``audit-report.md`` link. Reads the (transient, gitignored)
    ``audit-report.json``; degrades gracefully when it has not been run."""
    path = project_root / ".shipwright" / "compliance" / "audit-report.json"
    lines = ["## 🔎 Consistency Audit", ""]
    if not path.exists():
        lines.extend([
            "_Detective cross-artifact audit not run this session — "
            "run `/shipwright-compliance` to refresh._",
            "",
        ])
        return lines
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        findings = report.get("findings", [])
        passed = sum(1 for f in findings if f.get("status") == "pass")
        failed = sum(1 for f in findings if f.get("status") == "fail")
        skipped = sum(1 for f in findings if f.get("status") == "skip")
        verdict = "FAIL — drift found" if report.get("any_fail") else "PASS"
    except (OSError, json.JSONDecodeError, AttributeError):  # pragma: no cover
        lines.extend(["_Audit report present but unreadable._", ""])
        return lines

    date = _audit_generated_date(project_root)
    when = f" ({date})" if date else ""
    lines.extend([
        f"Detective audit{when}: **{verdict}** · "
        f"{len(findings)} checks — {passed} pass, {failed} fail, {skipped} skip.",
        "",
        "_Inlined from `audit-report.json` (a gitignored transient — no "
        "external link, so this stays visible on the public repo)._",
        "",
    ])
    return lines

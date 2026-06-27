"""Compliance Dashboard generator.

Produces .shipwright/compliance/dashboard.md — the single-page overview.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Cross-cutting markdown helper lives at shared/scripts/markdown_table.py
# (outside the `lib/` namespace per ADR-045 so it can be imported here
# without colliding with this plugin's own `lib/` regular package).
_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
from markdown_table import escape_cell  # noqa: E402

# Triage Inbox count surfaces in the dashboard's Quality Indicators
# section (Iterate B.1). Import is deferred to keep the test fixture
# fallback path simple — a project with no `.shipwright/triage.jsonl`
# yields an empty list, not a crash.
try:
    from triage import read_all_items as _read_triage_items  # noqa: E402
except ImportError:  # pragma: no cover - triage helper always available in practice
    _read_triage_items = None  # type: ignore[assignment]
from ._bloat_dashboard_rows import bloat_rows_events_mode, bloat_rows_legacy_mode  # B3
from ._control_block import latest_tests_row, render_consistency_audit, render_control_block  # AR-01/02/03
if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData


_COPYLEFT_LICENSES = {"GPL", "LGPL", "AGPL", "MPL-2.0", "GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0"}


def _is_adopted(run_config: dict) -> bool:
    """True when the project was onboarded via /shipwright-adopt.

    The empirically correct signal is the presence of the `adoption`
    object (carrying `adopted_at`, `commit_at_adoption`, ...). The
    artifact-polish plan originally suggested checking `scope`, but
    `scope` carries values like `"library"` / `"full_app"` — orthogonal
    to adoption status (Iterate B.1, 2026-05-21).
    """
    adoption = run_config.get("adoption")
    return isinstance(adoption, dict) and bool(adoption)


_SIGNAL_SEVERITIES = frozenset({"critical", "high", "medium", "low"})


def _triage_open_counts(project_root: Path) -> tuple[int, int]:
    """Return (signal_count, info_count) of open triage items.

    Signal = severity ∈ ``_SIGNAL_SEVERITIES`` (critical/high/medium/low).
    Info   = severity == "info".
    Items with malformed / missing / unknown severity are skipped from
    BOTH counts (ADR-055 D5 — tolerant reader, matches the schema enum
    boundary so future severity-vocab expansions don't auto-promote to
    signal until the dashboard is updated).
    """
    if _read_triage_items is None:
        return (0, 0)
    try:
        items = _read_triage_items(project_root)
    except Exception:  # pragma: no cover - tolerant of corrupt file
        return (0, 0)
    signal = 0
    info = 0
    for it in items:
        if it.get("status") != "triage":
            continue
        sev = it.get("severity")
        if sev in _SIGNAL_SEVERITIES:
            signal += 1
        elif sev == "info":
            info += 1
        # else: unknown severity → skipped silently per ADR-055 D5
    return (signal, info)


def generate(data: ComplianceData) -> str:
    """Generate Compliance Dashboard as Markdown string."""
    run_config = data.configs.get("run", {})
    profile = run_config.get("profile", "unknown")
    scope = run_config.get("scope", "unknown")

    lines = [
        "# Compliance Dashboard",
        "",
        f"Generated: {data.timestamp}",
        f"Profile: {profile}",
        f"Scope: {scope}",
        "",
    ]

    lines.extend(render_control_block(data))  # AR-01: Control Verdict + Grade

    # Quality indicators — event-based if events exist, legacy otherwise
    if data.work_events:
        lines.extend(_quality_indicators_events(data))
        lines.extend(_project_velocity(data))
    else:
        lines.extend(_quality_indicators_legacy(data))

    lines.extend(_external_review_evidence(data))
    lines.extend(render_consistency_audit(data.project_root))  # AR-03: inline audit

    # Compliance artifacts
    artifact_rows = [
        "| Traceability Matrix | [traceability-matrix.md](./traceability-matrix.md) | Requirements → Work Events → Tests |",
        "| Test Evidence | [test-evidence.md](./test-evidence.md) | Test progression timeline |",
        "| Commit Change Log | [change-history.md](./change-history.md) | Conventional Commits by type |",
        "| Decision Log | [decision_log.md](../agent_docs/decision_log.md) | Architecture decisions (ADRs) |",
        "| SBOM | [sbom.md](./sbom.md) | Open-source dependencies + licenses |",
        # AR-03: the audit report is gitignored (404 on the public repo), so we
        # inline its summary above instead of linking it (render_consistency_audit).
    ]
    # Activity / build dashboard (per-event change + pipeline view). Tracked, so
    # conditional-on-existence is stable (no flip-flop).
    if (data.project_root / ".shipwright" / "agent_docs" / "build_dashboard.md").exists():
        artifact_rows.append("| Activity Dashboard | [build_dashboard.md](../agent_docs/build_dashboard.md) | Per-event change history + pipeline status |")
    # Event log
    # NOTE: Reports now live at .shipwright/compliance/<file>.md (2-deep), so links
    # to project-root files use ../../ instead of ../. Sibling links under
    # .shipwright/ -- agent_docs and planning subdirs -- use the ../<sibling>/ form.
    if (data.project_root / "shipwright_events.jsonl").exists():
        artifact_rows.insert(0, "| Event Log | [shipwright_events.jsonl](../../shipwright_events.jsonl) | Unified append-only event log |")
    if (data.project_root / "CHANGELOG.md").exists():
        artifact_rows.append("| Changelog | [CHANGELOG.md](../../CHANGELOG.md) | Release notes |")
    if (data.project_root / "playwright-report" / "index.html").exists():
        artifact_rows.append("| Playwright Report | [playwright-report/index.html](../../playwright-report/index.html) | Interactive E2E test results |")
    if (data.project_root / "design-fidelity-report.json").exists():
        artifact_rows.append("| Design Fidelity Report | [design-fidelity-report.json](../../design-fidelity-report.json) | Per-screen design fidelity verification (build → test) |")
    elif (data.project_root / "visual-build-report.json").exists():
        artifact_rows.append("| Design Fidelity Report | [visual-build-report.json](../../visual-build-report.json) | Per-screen design fidelity verification (build → test, legacy) |")

    lines.extend([
        "## Compliance Artifacts",
        "",
        "| Document | Path | Description |",
        "|----------|------|-------------|",
        *artifact_rows,
        "",
    ])

    return "\n".join(lines) + "\n"


def _quality_indicators_events(data: ComplianceData) -> list[str]:
    """Quality indicators from event log.

    Iterate B.1 (2026-05-21) — three changes:
    - **Mode-aware**: adopted projects don't run the pipeline phases,
      so the "Pipeline phases completed" row renders ``n/a (adopted)``
      instead of a fake ``1/7 WARN``; the build-sections + sections-
      reviewed rows are hidden entirely (structurally N/A, not "not
      run yet").
    - **Why warn? column**: one-line diagnostic pointer on every WARN
      row so the operator knows where to look. Empty cell for PASS /
      INFO / n/a rows.
    - **Triage open indicator**: new row counting open items in
      ``.shipwright/triage.jsonl``. Signal severity (critical/high/
      medium/low) prominent; info-severity shown in parentheses
      consistent with the inbox's signal-first render (B0 ADR-054 D6).
    """
    run_config = data.configs.get("run", {})
    adopted = _is_adopted(run_config)

    build_events = [we for we in data.work_events if we.source == "build"]
    iterate_events = [we for we in data.work_events if we.source == "iterate"]

    # Phase completion from events
    completed_phases = [e["phase"] for e in data.phase_events if e.get("type") == "phase_completed"]
    total_pipeline = 7  # project, design, plan, build, test, changelog, deploy

    # Review counts
    reviewed = sum(1 for we in build_events if we.review_type)

    total_decisions = sum(len(e.decisions) for e in data.decisions)
    total_deps = len(data.dependencies)
    copyleft = sum(
        1 for d in data.dependencies
        if any(cl in d.license.upper() for cl in ("GPL", "AGPL", "LGPL", "MPL"))
    )

    # Iterate test coverage
    iterate_tested = sum(1 for we in iterate_events if we.tests_total > 0)

    # Triage open counts — signal vs info-severity (B0 ADR-054 D6).
    triage_signal, triage_info = _triage_open_counts(data.project_root)

    lines = [
        "## Quality Indicators",
        "",
        "| Metric | Value | Status | Why warn? |",
        "|--------|-------|--------|-----------|",
    ]

    # Pipeline phases — n/a for adopted, real progress for greenfield.
    if adopted:
        lines.append(
            "| Pipeline phases completed | n/a (adopted) | INFO |  |"
        )
    else:
        pipeline_ok = len(completed_phases) >= total_pipeline
        pipeline_status = _status_badge(pipeline_ok)
        pipeline_why = (
            f"{total_pipeline - len(completed_phases)} phase(s) pending — see shipwright_events.jsonl"
            if not pipeline_ok else ""
        )
        lines.append(
            f"| Pipeline phases completed | {len(completed_phases)}/{total_pipeline} | "
            f"{pipeline_status} | {pipeline_why} |"
        )

    # Build-sections + sections-reviewed: structurally N/A for adopted
    # (the project was onboarded with existing code, not built section
    # by section). Hide entirely instead of WARN-noise.
    if not adopted:
        build_ok = len(build_events) > 0
        build_why = (
            "no build events recorded — run /shipwright-build" if not build_ok else ""
        )
        lines.append(
            f"| Work events (build) | {len(build_events)} sections | "
            f"{_status_badge(build_ok)} | {build_why} |"
        )

    lines.append(
        f"| Work events (iterate) | {len(iterate_events)} changes | INFO |  |"
    )

    lines.append(latest_tests_row(data.work_events))  # AR-02: latest full suite

    if not adopted:
        review_ok = reviewed == len(build_events) and len(build_events) > 0
        if not review_ok:
            # Two WARN paths: (a) build_events==0 — pre-build greenfield;
            # (b) build_events>0 but some unreviewed. Both get a diagnostic
            # (ADR-055 D4 / AC-5: every WARN row carries a pointer).
            if len(build_events) == 0:
                review_why = "no build events yet — run /shipwright-build first"
            else:
                review_why = (
                    f"{len(build_events) - reviewed} section(s) unreviewed — "
                    "see change-history.md"
                )
        else:
            review_why = ""
        lines.append(
            f"| All sections reviewed | {reviewed}/{len(build_events)} | "
            f"{_status_badge(review_ok)} | {review_why} |"
        )

    lines.append(
        f"| Architecture decisions | {total_decisions} ADRs | INFO |  |"
    )

    if iterate_events:
        iter_ok = iterate_tested == len(iterate_events)
        iter_why = (
            f"{len(iterate_events) - iterate_tested} iterate(s) without tests — see test-evidence.md"
            if not iter_ok else ""
        )
        lines.append(
            f"| Iterate tests passing | {iterate_tested}/{len(iterate_events)} iterations tested | "
            f"{_status_badge(iter_ok)} | {iter_why} |"
        )

    lines.append(
        f"| Dependencies | {total_deps} packages | INFO |  |"
    )

    copyleft_why = (
        f"{copyleft} copyleft license(s) detected — see sbom.md"
        if copyleft > 0 else ""
    )
    lines.append(
        f"| Copyleft risk | {copyleft} | {_status_badge(copyleft == 0)} | {copyleft_why} |"
    )

    # Triage open — new B.1 indicator. WARN when any signal item is
    # open; info-only counts surface as PASS with a non-empty Value.
    triage_value = f"{triage_signal} open"
    if triage_info:
        triage_value += f" ({triage_info} info)"
    triage_ok = triage_signal == 0
    triage_why = (
        f"{triage_signal} actionable item(s) — see ../agent_docs/triage_inbox.md"
        if not triage_ok else ""
    )
    lines.append(
        f"| Triage open | {triage_value} | {_status_badge(triage_ok)} | {triage_why} |"
    )
    lines.extend(bloat_rows_events_mode(data.project_root))  # B3 (includes trailing "")
    return lines


def _project_velocity(data: ComplianceData) -> list[str]:
    """Project velocity computed from event timestamps."""
    build_events = [we for we in data.work_events if we.source == "build"]
    iterate_events = [we for we in data.work_events if we.source == "iterate"]

    lines = ["## Project Velocity", ""]

    if build_events:
        first_date = build_events[0].timestamp[:10]
        last_date = build_events[-1].timestamp[:10]
        lines.append(f"- Build: {len(build_events)} sections ({first_date} → {last_date})")

    if iterate_events:
        first_date = iterate_events[0].timestamp[:10]
        last_date = iterate_events[-1].timestamp[:10]
        lines.append(f"- Iterate: {len(iterate_events)} changes ({first_date} → {last_date})")

    if data.work_events:
        lines.append(f"- Last activity: {data.work_events[-1].timestamp[:10]}")

    lines.append("")
    return lines


def _external_review_evidence(data: ComplianceData) -> list[str]:
    """External LLM review audit evidence — one row per planning split.

    Reads the markers written by shipwright-plan v0.3.0+ Step 5. Splits with
    no marker are shown as "missing" so auditors can see the gap.
    """
    if not data.external_review_states:
        return []

    lines = [
        "## External LLM Review Evidence",
        "",
        "| Split | Status | Provider | Findings | Self-review fallback | Reason |",
        "|-------|--------|----------|----------|----------------------|--------|",
    ]
    for s in data.external_review_states:
        provider = s.provider or "—"
        fallback = "yes" if s.self_review_fallback_ran else "no"
        reason = s.reason or "—"
        lines.append(
            f"| {escape_cell(s.split)} | {escape_cell(s.status)} | {escape_cell(provider)} "
            f"| {s.findings_count} | {fallback} | {escape_cell(reason)} |"
        )
    lines.append("")
    return lines


def _quality_indicators_legacy(data: ComplianceData) -> list[str]:
    """Legacy quality indicators from config files."""
    total_sections = len(data.sections)
    completed = sum(1 for s in data.sections if s.status == "complete")
    total_passed = sum(s.tests_passed for s in data.sections)
    total_tests = sum(s.tests_total for s in data.sections)
    reviewed = total_sections
    total_decisions = sum(len(e.decisions) for e in data.decisions)
    total_deps = len(data.dependencies)
    copyleft = sum(
        1 for d in data.dependencies
        if any(cl in d.license.upper() for cl in ("GPL", "AGPL", "LGPL", "MPL"))
    )

    return [
        "## Quality Indicators",
        "",
        "| Indicator | Value | Status | Description |",
        "|-----------|-------|--------|-------------|",
        f"| All planned splits built | {len(data.splits)} | {_status_badge(len(data.splits) > 0)} | Every project split has been implemented |",
        f"| All sections completed | {completed}/{total_sections} | {_status_badge(completed == total_sections and total_sections > 0)} | Build sections across all splits |",
        f"| All unit tests passing | {total_passed}/{total_tests} | {_status_badge(total_passed == total_tests and total_tests > 0)} | Unit tests across all sections |",
        f"| Code reviewed | {reviewed}/{total_sections} sections | {_status_badge(reviewed == total_sections and total_sections > 0)} | Sections that went through code review |",
        f"| Architecture decisions logged | {total_decisions} | INFO | ADR entries in decision_log.md |",
        f"| Third-party dependencies | {total_deps} | INFO | Open-source packages in use |",
        f"| Copyleft license risk | {copyleft} | {_status_badge(copyleft == 0)} | Packages with GPL/AGPL/LGPL/MPL licenses |",
        *bloat_rows_legacy_mode(data.project_root),  # B3
        "",
    ]


COMPLIANCE_DIR = ".shipwright/compliance"
LEGACY_COMPLIANCE_DIRNAME = "compliance"


def generate_file(project_root: Path, data: ComplianceData | None = None) -> Path:
    """Generate Dashboard and write to .shipwright/compliance/dashboard.md."""
    if data is None:
        from scripts.lib.data_collector import collect_all
        data = collect_all(project_root)

    output_dir = project_root / COMPLIANCE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "dashboard.md"
    output_path.write_text(generate(data), encoding="utf-8")
    return output_path


def _status_badge(ok: bool) -> str:
    """Return PASS or WARN text."""
    return "PASS" if ok else "WARN"

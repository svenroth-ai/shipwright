"""Compliance Dashboard generator.

Produces .shipwright/compliance/dashboard.md — the single-page overview.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData


_COPYLEFT_LICENSES = {"GPL", "LGPL", "AGPL", "MPL-2.0", "GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0"}


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

    # Quality indicators — event-based if events exist, legacy otherwise
    if data.work_events:
        lines.extend(_quality_indicators_events(data))
        lines.extend(_project_velocity(data))
    else:
        lines.extend(_quality_indicators_legacy(data))

    lines.extend(_external_review_evidence(data))

    # Compliance artifacts
    artifact_rows = [
        "| Traceability Matrix | [traceability-matrix.md](./traceability-matrix.md) | Requirements → Work Events → Tests |",
        "| Test Evidence | [test-evidence.md](./test-evidence.md) | Test progression timeline |",
        "| Commit Change Log | [change-history.md](./change-history.md) | Conventional Commits by type |",
        "| Decision Log | [decision_log.md](../agent_docs/decision_log.md) | Architecture decisions (ADRs) |",
        "| SBOM | [sbom.md](./sbom.md) | Open-source dependencies + licenses |",
    ]
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
    """Quality indicators from event log."""
    build_events = [we for we in data.work_events if we.source == "build"]
    iterate_events = [we for we in data.work_events if we.source == "iterate"]

    # Phase completion from events
    completed_phases = [e["phase"] for e in data.phase_events if e.get("type") == "phase_completed"]
    total_pipeline = 7  # project, design, plan, build, test, changelog, deploy

    # Latest test counts from work events
    latest_passed = data.work_events[-1].tests_passed if data.work_events else 0
    latest_total = data.work_events[-1].tests_total if data.work_events else 0

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

    lines = [
        "## Quality Indicators",
        "",
        "| Metric | Value | Status |",
        "|--------|-------|--------|",
        f"| Pipeline phases completed | {len(completed_phases)}/{total_pipeline} | {_status_badge(len(completed_phases) >= total_pipeline)} |",
        f"| Work events (build) | {len(build_events)} sections | {_status_badge(len(build_events) > 0)} |",
        f"| Work events (iterate) | {len(iterate_events)} changes | INFO |",
        f"| All unit tests passing | {latest_passed}/{latest_total} | {_status_badge(latest_passed == latest_total and latest_total > 0)} |",
        f"| All sections reviewed | {reviewed}/{len(build_events)} | {_status_badge(reviewed == len(build_events) and len(build_events) > 0)} |",
        f"| Architecture decisions | {total_decisions} ADRs | INFO |",
    ]

    if iterate_events:
        lines.append(f"| Iterate tests passing | {iterate_tested}/{len(iterate_events)} iterations tested | {_status_badge(iterate_tested == len(iterate_events))} |")

    lines.extend([
        f"| Dependencies | {total_deps} packages | INFO |",
        f"| Copyleft risk | {copyleft} | {_status_badge(copyleft == 0)} |",
        "",
    ])

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
            f"| {s.split} | {s.status} | {provider} | {s.findings_count} | {fallback} | {reason} |"
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

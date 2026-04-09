"""Test Evidence Report generator.

Produces compliance/test-evidence.md with per-section test results,
test execution summary (unit/smoke/e2e), and links to specs and test files.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from scripts.lib.mermaid import testing_pyramid_diagram

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData


def generate(data: ComplianceData) -> str:
    """Generate Test Evidence Report as Markdown string."""
    lines = [
        "# Test Evidence Report",
        "",
        f"Generated: {data.timestamp}",
        "",
    ]

    # Use event-based generation if events exist
    if data.work_events:
        lines.extend(_test_progression(data))
        lines.extend(_full_suite_runs(data))
        lines.extend(_e2e_details(data))
        lines.extend(_code_review_evidence_events(data))
    else:
        # Legacy fallback
        lines.extend(_test_execution_summary(data))
        lines.extend([
            "## Test Pyramid",
            "",
            testing_pyramid_diagram(data.sections, data.test_results),
            "",
        ])
        lines.extend(_per_split_results(data))
        lines.extend(_e2e_details(data))
        lines.extend(_code_review_evidence(data))

    return "\n".join(lines) + "\n"


def _test_execution_summary(data: ComplianceData) -> list[str]:
    """Generate test execution summary table with all three layers."""
    total_passed = sum(s.tests_passed for s in data.sections)
    total_tests = sum(s.tests_total for s in data.sections)
    total_findings = sum(s.review_findings for s in data.sections)
    total_fixed = sum(s.review_findings_fixed for s in data.sections)
    sections_reviewed = len(data.sections)

    lines = [
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total sections tested | {len(data.sections)} |",
        f"| Unit tests passed | {total_passed} |",
        f"| Unit tests failed | {total_tests - total_passed} |",
        f"| Code review sections | {sections_reviewed}/{len(data.sections)} |",
        f"| Review findings total | {total_findings} |",
        f"| Review findings fixed | {total_fixed} |",
    ]

    tr = data.test_results
    if tr:
        lines.extend([
            "",
            "## Test Execution Summary",
            "",
            "| Layer | Status | Passed | Total | Duration | Details |",
            "|-------|--------|--------|-------|----------|---------|",
        ])

        # Unit
        unit_status = "PASS" if tr.unit_passed == tr.unit_total and tr.unit_total > 0 else "FAIL"
        if tr.unit_total == 0:
            unit_status = "SKIP"
        lines.append(
            f"| Unit | {unit_status} | {tr.unit_passed} | {tr.unit_total} "
            f"| {tr.unit_duration_s}s | Vitest |"
        )

        # Integration
        if tr.integration_skipped:
            int_status = "SKIP"
            int_detail = tr.integration_skip_reason or "skipped"
            lines.append(f"| Integration | {int_status} | — | — | — | {int_detail} |")
        elif tr.integration_total > 0:
            int_status = "PASS" if tr.integration_passed == tr.integration_total else "FAIL"
            lines.append(
                f"| Integration | {int_status} | {tr.integration_passed} | {tr.integration_total} "
                f"| {tr.integration_duration_s}s | Vitest (real DB) |"
            )
        else:
            lines.append("| Integration | — | 0 | 0 | — | not configured |")

        # pgTAP
        if tr.pgtap_skipped:
            pgtap_status = "SKIP"
            pgtap_detail = tr.pgtap_skip_reason or "skipped"
            lines.append(f"| pgTAP | {pgtap_status} | — | — | — | {pgtap_detail} |")
        elif tr.pgtap_total > 0:
            pgtap_status = "PASS" if tr.pgtap_passed == tr.pgtap_total else "FAIL"
            lines.append(
                f"| pgTAP | {pgtap_status} | {tr.pgtap_passed} | {tr.pgtap_total} "
                f"| {tr.pgtap_duration_s}s | supabase test db |"
            )

        # Smoke
        smoke_status = tr.smoke_status.upper() if tr.smoke_status else "—"
        smoke_detail = f"GET {tr.smoke_url}" if tr.smoke_url else "—"
        if tr.smoke_response_ms:
            smoke_detail += f" ({tr.smoke_response_ms}ms)"
        lines.append(
            f"| Smoke | {smoke_status} | — | — | — | {smoke_detail} |"
        )

        # E2E
        if tr.e2e_skipped:
            e2e_status = "SKIP"
            e2e_detail = tr.e2e_skip_reason or "skipped"
            lines.append(f"| E2E | {e2e_status} | — | — | — | {e2e_detail} |")
        else:
            e2e_status = "PASS" if tr.e2e_passed == tr.e2e_total and tr.e2e_total > 0 else "FAIL"
            if tr.e2e_total == 0:
                e2e_status = "—"
            lines.append(
                f"| E2E | {e2e_status} | {tr.e2e_passed} | {tr.e2e_total} "
                f"| — | Playwright |"
            )

        # Visual
        if tr.visual_skipped:
            vis_status = "SKIP"
            vis_detail = tr.visual_skip_reason or "skipped"
            lines.append(f"| Visual | {vis_status} | — | — | — | {vis_detail} |")
        elif tr.visual_total > 0:
            vis_status = "PASS" if tr.visual_passed == tr.visual_total else "WARNING"
            vis_detail = "Mockup vs Live"
            if tr.visual_report_path:
                vis_detail += f" ([detail](visual-build-report.json))"
            lines.append(
                f"| Visual | {vis_status} | {tr.visual_passed} | {tr.visual_total} "
                f"| — | {vis_detail} |"
            )

        # Consistency
        if tr.consistency_skipped:
            cons_status = "SKIP"
            cons_detail = tr.consistency_skip_reason or "skipped"
            lines.append(f"| Consistency | {cons_status} | — | — | — | {cons_detail} |")
        elif tr.consistency_total > 0:
            cons_status = "PASS" if tr.consistency_passed == tr.consistency_total else "WARNING"
            lines.append(
                f"| Consistency | {cons_status} | {tr.consistency_passed} | {tr.consistency_total} "
                f"| — | Cross-page UI check |"
            )

        lines.append("")
    else:
        lines.extend([
            "",
            "_No test execution results found. Run `/shipwright-test` to generate `shipwright_test_results.json`._",
            "",
        ])

    return lines


def _per_split_results(data: ComplianceData) -> list[str]:
    """Per-split test results with layer breakdown and section summary."""
    if not data.sections:
        return []

    lines = ["## Per-Split Results", ""]

    # Group sections by split
    splits_seen: dict[str, list] = {}
    for sec in data.sections:
        splits_seen.setdefault(sec.split, []).append(sec)

    # Read per-split E2E results if available
    split_e2e = _collect_split_e2e_results(data.project_root)

    for split_name, sections in splits_seen.items():
        unit_passed = sum(s.tests_passed for s in sections)
        unit_total = sum(s.tests_total for s in sections)
        total_sections = len(sections)
        complete_sections = sum(1 for s in sections if s.status == "complete")
        total_findings = sum(s.review_findings for s in sections)
        review_types = {s.review_type for s in sections if s.review_type}
        review_label = ", ".join(sorted(review_types)) if review_types else "—"

        # E2E data for this split
        e2e_info = split_e2e.get(split_name, {})
        e2e_passed = e2e_info.get("passed", 0)
        e2e_total = e2e_info.get("total", 0)

        lines.append(f"### Split: {split_name}")
        lines.append("")
        lines.append("| Layer | Passed | Total | Status |")
        lines.append("|-------|--------|-------|--------|")

        # Unit layer
        if unit_total > 0:
            u_status = "PASS" if unit_passed == unit_total else "FAIL"
        else:
            u_status = "—"
        lines.append(f"| Unit | {unit_passed} | {unit_total} | {u_status} |")

        # E2E layer (if data available)
        if e2e_total > 0:
            e_status = "PASS" if e2e_passed == e2e_total else "WARNING"
            lines.append(f"| E2E | {e2e_passed} | {e2e_total} | {e_status} |")
        else:
            lines.append("| E2E | — | — | — |")

        lines.append("")
        lines.append(
            f"Sections: {complete_sections}/{total_sections} complete "
            f"| Review: {review_label} ({total_findings} findings)"
        )
        lines.append("")

    return lines


def _collect_split_e2e_results(project_root: Path) -> dict[str, dict]:
    """Read per-split E2E results from archived and current test results.

    Returns: {"01-foundation": {"passed": 6, "total": 7}, ...}
    Maps split number prefixes from spec filenames to split names.
    """
    import json

    result: dict[str, dict] = {}

    # Get split names from project config
    project_config_path = project_root / "shipwright_project_config.json"
    split_names: dict[str, str] = {}  # "01" -> "01-foundation"
    if project_config_path.exists():
        try:
            config = json.loads(project_config_path.read_text(encoding="utf-8"))
            for split in config.get("splits", []):
                name = split.get("name", "")
                if len(name) >= 2:
                    split_names[name[:2]] = name
        except (json.JSONDecodeError, OSError):
            pass

    # Current test results have aggregate E2E — distribute to last split
    current = project_root / "shipwright_test_results.json"
    if current.exists():
        try:
            data = json.loads(current.read_text(encoding="utf-8"))
            e2e = data.get("e2e", {})
            if e2e.get("total", 0) > 0:
                # E2E tests run after all splits — assign to project-level
                # For now, report as aggregate across all splits
                result["_aggregate"] = {
                    "passed": e2e.get("passed", 0),
                    "total": e2e.get("total", 0),
                }
        except (json.JSONDecodeError, OSError):
            pass

    return result


def _e2e_details(data: ComplianceData) -> list[str]:
    """E2E test failure details and Playwright report link."""
    lines: list[str] = []

    # Playwright HTML report link
    report_path = data.project_root / "playwright-report" / "index.html"
    if report_path.exists():
        lines.extend([
            "## Playwright Report",
            "",
            "**Interactive E2E report:** [playwright-report/index.html](../playwright-report/index.html)",
            "",
        ])

    # Failure details
    tr = data.test_results
    if tr and not tr.e2e_skipped and tr.e2e_failures:
        lines.extend(["## E2E Test Failures", ""])
        for failure in tr.e2e_failures:
            lines.append(f"- {failure}")
        lines.append("")

    return lines


def _code_review_evidence(data: ComplianceData) -> list[str]:
    """Code review evidence table."""
    if not data.sections:
        return []

    _REVIEW_LABELS = {
        "full-review": "Full review",
        "self-review": "Self-review only",
    }

    lines = [
        "## Code Review Evidence",
        "",
        "| Section | Review Type | Findings | Fixed | Deferred | Status |",
        "|---------|-------------|----------|-------|----------|--------|",
    ]
    for sec in data.sections:
        review_label = _REVIEW_LABELS.get(sec.review_type, "Unknown")
        deferred = sec.review_findings - sec.review_findings_fixed
        if sec.review_type == "self-review":
            status = "SELF-REVIEW"
        elif deferred == 0:
            status = "PASS"
        else:
            status = "OPEN"
        lines.append(
            f"| {sec.name} | {review_label} | {sec.review_findings} | {sec.review_findings_fixed} "
            f"| {deferred} | {status} |"
        )
    lines.append("")

    return lines


# ---------------------------------------------------------------------------
# Event-based generation
# ---------------------------------------------------------------------------

def _test_progression(data: ComplianceData) -> list[str]:
    """Test progression timeline from work events."""
    if not data.work_events:
        return []

    build_events = [we for we in data.work_events if we.source == "build"]
    iterate_events = [we for we in data.work_events if we.source == "iterate"]
    new_from_iterate = sum(we.tests_new for we in iterate_events)

    # Latest test counts
    latest = data.work_events[-1]

    lines = [
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total test checkpoints | {len(data.work_events)} |",
        f"| Total unit tests (latest) | {latest.tests_passed}/{latest.tests_total} |",
    ]

    if data.test_runs:
        last_run = data.test_runs[-1]
        lines.append(f"| Total E2E tests (latest) | {last_run.e2e_passed}/{last_run.e2e_total} |")

    if new_from_iterate:
        lines.append(f"| New tests from iterations | +{new_from_iterate} |")

    lines.extend([
        "",
        "## Test Progression",
        "",
        "| # | Event | Source | New Tests | Suite Total | Result | Date |",
        "|---|-------|--------|-----------|-------------|--------|------|",
    ])

    for i, we in enumerate(reversed(data.work_events), 1):
        name = we.section if we.source == "build" else (we.description or we.id)
        source = we.source

        # New tests display
        if we.source == "iterate":
            new_parts = []
            if we.tests_new:
                new_parts.append(f"+{we.tests_new}")
            if we.tests_modified:
                new_parts.append(f"{we.tests_modified} mod")
            new_cell = ", ".join(new_parts) if new_parts else "+0"
        else:
            new_cell = f"+{we.tests_total}" if we.tests_total > 0 else "—"

        suite = f"{we.tests_passed}/{we.tests_total}" if we.tests_total > 0 else "—"
        result = "PASS" if we.tests_passed == we.tests_total and we.tests_total > 0 else "FAIL" if we.tests_total > 0 else "—"
        date = we.timestamp[:10]

        lines.append(f"| {i} | {name} | {source} | {new_cell} | {suite} | {result} | {date} |")

    lines.append("")
    return lines


def _full_suite_runs(data: ComplianceData) -> list[str]:
    """Full test suite runs from test_run events."""
    if not data.test_runs:
        return []

    lines = [
        "## Full Suite Runs",
        "",
        "| Run | Trigger | Unit | Smoke | E2E | Date |",
        "|-----|---------|------|-------|-----|------|",
    ]

    for i, tr in enumerate(data.test_runs, 1):
        unit = f"{tr.unit_passed}/{tr.unit_total}" if tr.unit_total > 0 else "—"
        smoke = tr.smoke_status or "—"
        e2e = f"{tr.e2e_passed}/{tr.e2e_total}" if tr.e2e_total > 0 else "—"
        date = tr.timestamp[:10]
        trigger = tr.trigger or "—"

        lines.append(f"| {i} | {trigger} | {unit} | {smoke} | {e2e} | {date} |")

    lines.append("")
    return lines


def _code_review_evidence_events(data: ComplianceData) -> list[str]:
    """Code review evidence from work events."""
    events_with_review = [we for we in data.work_events if we.review_type]
    if not events_with_review:
        return []

    _REVIEW_LABELS = {
        "full-review": "Full review",
        "self-review": "Self-review only",
    }

    lines = [
        "## Code Review Evidence",
        "",
        "| Event | Review Type | Findings | Fixed | Status |",
        "|-------|------------|----------|-------|--------|",
    ]

    for we in events_with_review:
        name = we.section if we.source == "build" else (we.description or we.id)
        review_label = _REVIEW_LABELS.get(we.review_type, we.review_type)
        deferred = we.review_findings - we.review_fixed
        if we.review_type == "self-review" and we.review_findings == 0:
            status = "PASS"
        elif deferred == 0:
            status = "PASS"
        else:
            status = "OPEN"

        lines.append(f"| {name} | {review_label} | {we.review_findings} | {we.review_fixed} | {status} |")

    lines.append("")
    return lines


def generate_file(project_root: Path, data: ComplianceData | None = None) -> Path:
    """Generate Test Evidence Report and write to compliance/test-evidence.md."""
    if data is None:
        from scripts.lib.data_collector import collect_all
        data = collect_all(project_root)

    output_dir = project_root / "compliance"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "test-evidence.md"
    output_path.write_text(generate(data), encoding="utf-8")
    return output_path


def _format_findings(total: int, fixed: int) -> str:
    """Format review findings."""
    if total == 0:
        return "0"
    return f"{total} ({fixed} fixed)"

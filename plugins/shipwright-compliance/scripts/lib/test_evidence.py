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

    # --- Test Execution Summary (unit + smoke + e2e) ---
    lines.extend(_test_execution_summary(data))

    # --- Per-section unit test results ---
    lines.extend(_per_section_results(data))

    # --- E2E Test Details ---
    lines.extend(_e2e_details(data))

    # --- Test Pyramid ---
    lines.extend([
        "## Test Pyramid",
        "",
        testing_pyramid_diagram(data.sections, data.test_results),
        "",
    ])

    # --- Code Review Evidence ---
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

        lines.append("")
    else:
        lines.extend([
            "",
            "_No test execution results found. Run `/shipwright-test` to generate `shipwright_test_results.json`._",
            "",
        ])

    return lines


def _per_section_results(data: ComplianceData) -> list[str]:
    """Per-section unit test results with links to section plans and test files."""
    if not data.sections:
        return []

    lines = ["## Per-Section Results", ""]

    # Group by split
    splits_seen: dict[str, list] = {}
    for sec in data.sections:
        splits_seen.setdefault(sec.split, []).append(sec)

    for split_name, sections in splits_seen.items():
        lines.extend([
            f"### Split: {split_name}",
            "",
            "| Section | Tests Passed | Tests Total | Review Findings | Status |",
            "|---------|-------------|-------------|-----------------|--------|",
        ])
        for sec in sections:
            findings_text = _format_findings(sec.review_findings, sec.review_findings_fixed)
            status = "PASS" if sec.tests_passed == sec.tests_total and sec.tests_total > 0 else "PENDING"

            # Link to section plan file
            section_link = f"[{sec.name}](../planning/{split_name}/sections/{sec.name}.md)"

            lines.append(
                f"| {section_link} | {sec.tests_passed} | {sec.tests_total} "
                f"| {findings_text} | {status} |"
            )
        lines.append("")

    return lines


def _e2e_details(data: ComplianceData) -> list[str]:
    """E2E test failure details if available."""
    tr = data.test_results
    if not tr or tr.e2e_skipped or not tr.e2e_failures:
        return []

    lines = [
        "## E2E Test Failures",
        "",
    ]
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

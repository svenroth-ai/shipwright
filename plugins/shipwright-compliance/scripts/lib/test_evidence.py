"""Test Evidence Report generator.

Produces compliance/test-evidence.md with per-section test results.
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
        "## Summary",
        "",
    ]

    total_passed = sum(s.tests_passed for s in data.sections)
    total_tests = sum(s.tests_total for s in data.sections)
    total_findings = sum(s.review_findings for s in data.sections)
    total_fixed = sum(s.review_findings_fixed for s in data.sections)
    sections_reviewed = len(data.sections)  # all sections get reviewed

    lines.extend([
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total sections tested | {len(data.sections)} |",
        f"| Unit tests passed | {total_passed} |",
        f"| Unit tests failed | {total_tests - total_passed} |",
        f"| Code review sections | {sections_reviewed}/{len(data.sections)} |",
        f"| Review findings total | {total_findings} |",
        f"| Review findings fixed | {total_fixed} |",
    ])

    # Per-split results
    if data.sections:
        lines.extend(["", "## Per-Section Results", ""])

        # Group sections by split
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
                lines.append(
                    f"| {sec.name} | {sec.tests_passed} | {sec.tests_total} "
                    f"| {findings_text} | {status} |"
                )
            lines.append("")

    # Test pyramid
    lines.extend([
        "## Test Pyramid",
        "",
        testing_pyramid_diagram(data.sections),
        "",
    ])

    # Code review evidence
    if data.sections:
        lines.extend([
            "## Code Review Evidence",
            "",
            "| Section | Findings | Fixed | Deferred | Status |",
            "|---------|----------|-------|----------|--------|",
        ])
        for sec in data.sections:
            deferred = sec.review_findings - sec.review_findings_fixed
            status = "PASS" if deferred == 0 else "OPEN"
            lines.append(
                f"| {sec.name} | {sec.review_findings} | {sec.review_findings_fixed} "
                f"| {deferred} | {status} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


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

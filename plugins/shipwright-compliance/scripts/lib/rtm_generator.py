"""Requirements Traceability Matrix generator.

Produces compliance/traceability-matrix.md mapping:
  Splits → Sections → Commits → Test Results
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData


def generate(data: ComplianceData) -> str:
    """Generate RTM as a Markdown string."""
    lines = [
        "# Requirements Traceability Matrix",
        "",
        f"Generated: {data.timestamp}",
        "",
        "## Matrix",
        "",
    ]

    if not data.sections:
        lines.append("_No sections available yet. Run /shipwright-build to populate._")
    else:
        # Table header
        lines.append(
            "| Split | Section | Commit | Tests Passed | Tests Total "
            "| Review Findings | Status |"
        )
        lines.append(
            "|-------|---------|--------|-------------|-------------|"
            "-----------------|--------|"
        )

        for sec in data.sections:
            commit = sec.commit[:12] if sec.commit else "—"
            findings_detail = _format_findings(sec.review_findings, sec.review_findings_fixed)
            status = _section_status(sec)
            lines.append(
                f"| {sec.split} | {sec.name} | {commit} | {sec.tests_passed} "
                f"| {sec.tests_total} | {findings_detail} | {status} |"
            )

    # Summary
    lines.extend(["", "## Summary", ""])

    total_splits = len(data.splits)
    total_sections = len(data.sections)
    sections_with_commits = sum(1 for s in data.sections if s.commit)
    sections_passing = sum(
        1 for s in data.sections if s.tests_total > 0 and s.tests_passed == s.tests_total
    )
    total_findings = sum(s.review_findings for s in data.sections)
    unresolved = sum(s.review_findings - s.review_findings_fixed for s in data.sections)

    if total_sections > 0:
        coverage_pct = int(sections_with_commits / total_sections * 100)
    else:
        coverage_pct = 0

    lines.extend([
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total splits | {total_splits} |",
        f"| Total sections | {total_sections} |",
        f"| Sections with commits | {sections_with_commits} |",
        f"| Sections with passing tests | {sections_passing} |",
        f"| Total review findings | {total_findings} |",
        f"| Unresolved findings | {unresolved} |",
        f"| Traceability coverage | {coverage_pct}% |",
    ])

    return "\n".join(lines) + "\n"


def generate_file(project_root: Path, data: ComplianceData | None = None) -> Path:
    """Generate RTM and write to compliance/traceability-matrix.md."""
    if data is None:
        from scripts.lib.data_collector import collect_all
        data = collect_all(project_root)

    output_dir = project_root / "compliance"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "traceability-matrix.md"
    output_path.write_text(generate(data), encoding="utf-8")
    return output_path


def _format_findings(total: int, fixed: int) -> str:
    """Format review findings as 'N (M fixed)'."""
    if total == 0:
        return "0"
    deferred = total - fixed
    parts = []
    if fixed:
        parts.append(f"{fixed} fixed")
    if deferred:
        parts.append(f"{deferred} deferred")
    return f"{total} ({', '.join(parts)})"


def _section_status(sec) -> str:
    """Determine display status for a section."""
    if sec.status != "complete":
        return sec.status.upper()
    if sec.tests_total == 0:
        return "NO TESTS"
    if sec.tests_passed == sec.tests_total:
        return "PASS"
    return "FAIL"

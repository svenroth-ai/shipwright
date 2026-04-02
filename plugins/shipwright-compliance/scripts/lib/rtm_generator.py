"""Requirements Traceability Matrix generator.

Produces compliance/traceability-matrix.md mapping:
  Requirements → Sections → Commits → Test Results
with clickable links to spec files, section plans, and test files.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData, SectionInfo


def generate(data: ComplianceData) -> str:
    """Generate RTM as a Markdown string."""
    lines = [
        "# Requirements Traceability Matrix",
        "",
        f"Generated: {data.timestamp}",
        "",
    ]

    # --- Requirements Coverage Matrix ---
    lines.extend(_requirements_coverage(data))

    # --- Section Traceability ---
    lines.extend(_section_traceability(data))

    # --- Coverage Summary ---
    lines.extend(_coverage_summary(data))

    return "\n".join(lines) + "\n"


def _requirements_coverage(data: ComplianceData) -> list[str]:
    """Requirements coverage matrix with links to specs and sections."""
    if not data.requirements:
        return []

    # Build section lookup for test counts
    section_lookup: dict[str, SectionInfo] = {s.name: s for s in data.sections}

    lines = [
        "## Requirements Coverage",
        "",
        "| Requirement | Title | Priority | Section(s) | Unit Tests | Status |",
        "|-------------|-------|----------|------------|------------|--------|",
    ]

    for req in data.requirements:
        # Link to spec file with anchor
        anchor = _make_anchor(req.id)
        req_link = f"[{req.id}](../{req.spec_path}#{anchor})"

        # Truncated title for table readability
        display_text = req.text[:60] + ("..." if len(req.text) > 60 else "")

        # Linked sections
        if req.sections:
            section_links = []
            for sec_name in req.sections:
                sec_link = f"[{sec_name}](../planning/{req.split}/sections/{sec_name}.md)"
                section_links.append(sec_link)
            sections_cell = ", ".join(section_links)

            # Aggregate test counts from linked sections
            total_passed = 0
            total_tests = 0
            for sec_name in req.sections:
                sec = section_lookup.get(sec_name)
                if sec:
                    total_passed += sec.tests_passed
                    total_tests += sec.tests_total

            if total_tests > 0:
                tests_cell = f"{total_passed}/{total_tests}"
                status = "PASS" if total_passed == total_tests else "FAIL"
            else:
                tests_cell = "—"
                status = "NO TESTS"
        else:
            sections_cell = "—"
            tests_cell = "—"
            status = "UNLINKED"

        lines.append(
            f"| {req_link} | {display_text} | {req.priority} | {sections_cell} | {tests_cell} | {status} |"
        )

    lines.append("")
    return lines


def _section_traceability(data: ComplianceData) -> list[str]:
    """Section traceability table with requirement links."""
    lines = [
        "## Section Traceability",
        "",
    ]

    if not data.sections:
        lines.append("_No sections available yet. Run /shipwright-build to populate._")
        return lines

    # Build requirement lookup: section -> [req IDs]
    req_by_section: dict[str, list[str]] = {}
    for req in data.requirements:
        for sec_name in req.sections:
            req_by_section.setdefault(sec_name, []).append(req.id)

    lines.extend([
        "| Split | Section | Requirements | Commit | Tests | Status |",
        "|-------|---------|-------------|--------|-------|--------|",
    ])

    for sec in data.sections:
        commit = sec.commit[:12] if sec.commit else "—"
        status = _section_status(sec)

        # Link to section plan
        section_link = f"[{sec.name}](../planning/{sec.split}/sections/{sec.name}.md)"

        # Linked requirements
        reqs = req_by_section.get(sec.name, [])
        reqs_cell = ", ".join(reqs) if reqs else "—"

        # Tests
        if sec.tests_total > 0:
            tests_cell = f"{sec.tests_passed}/{sec.tests_total}"
        else:
            tests_cell = "—"

        lines.append(
            f"| {sec.split} | {section_link} | {reqs_cell} | {commit} "
            f"| {tests_cell} | {status} |"
        )

    lines.append("")
    return lines


def _coverage_summary(data: ComplianceData) -> list[str]:
    """Coverage summary metrics."""
    lines = ["## Coverage Summary", ""]

    total_sections = len(data.sections)
    sections_with_commits = sum(1 for s in data.sections if s.commit)
    sections_passing = sum(
        1 for s in data.sections if s.tests_total > 0 and s.tests_passed == s.tests_total
    )

    if total_sections > 0:
        coverage_pct = int(sections_with_commits / total_sections * 100)
    else:
        coverage_pct = 0

    lines.extend([
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total splits | {len(data.splits)} |",
        f"| Total sections | {total_sections} |",
        f"| Sections with commits | {sections_with_commits} |",
        f"| Sections with passing tests | {sections_passing} |",
        f"| Traceability coverage | {coverage_pct}% |",
    ])

    # Requirements coverage
    if data.requirements:
        total_reqs = len(data.requirements)
        must_reqs = [r for r in data.requirements if r.priority == "Must"]
        linked_reqs = [r for r in data.requirements if r.sections]
        linked_must = [r for r in must_reqs if r.sections]

        lines.extend([
            f"| Requirements total | {total_reqs} |",
            f"| Requirements linked to sections | {len(linked_reqs)}/{total_reqs} |",
            f"| Must-have requirements linked | {len(linked_must)}/{len(must_reqs)} |",
        ])

        # List uncovered requirements
        unlinked = [r for r in data.requirements if not r.sections]
        if unlinked:
            lines.extend(["", "### Unlinked Requirements", ""])
            for req in unlinked:
                lines.append(f"- [{req.id}](../{req.spec_path}) ({req.priority}): {req.text[:80]}...")

    # Review findings
    total_findings = sum(s.review_findings for s in data.sections)
    unresolved = sum(s.review_findings - s.review_findings_fixed for s in data.sections)
    lines.extend([
        f"| Total review findings | {total_findings} |",
        f"| Unresolved findings | {unresolved} |",
    ])

    lines.append("")
    return lines


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


def _make_anchor(fr_id: str) -> str:
    """Convert FR-02.01 to a Markdown heading anchor like 'fr-0201-...'."""
    # GitHub-style anchor: lowercase, remove dots, add hyphens
    return fr_id.lower().replace(".", "")


def _section_status(sec) -> str:
    """Determine display status for a section."""
    if sec.status != "complete":
        return sec.status.upper()
    if sec.tests_total == 0:
        return "NO TESTS"
    if sec.tests_passed == sec.tests_total:
        return "PASS"
    return "FAIL"

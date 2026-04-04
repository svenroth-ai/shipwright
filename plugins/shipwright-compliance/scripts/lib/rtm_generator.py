"""Requirements Traceability Matrix generator.

Produces compliance/traceability-matrix.md mapping:
  Requirements → Work Events (sections + iterations) → Test Results
with clickable links to spec files and verification timeline.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData, SectionInfo, WorkEvent


def generate(data: ComplianceData) -> str:
    """Generate RTM as a Markdown string."""
    lines = [
        "# Requirements Traceability Matrix",
        "",
        f"Generated: {data.timestamp}",
        "",
    ]

    # Use event-based generation if events exist
    if data.work_events:
        lines.extend(_requirements_coverage_events(data))
        lines.extend(_verification_timeline(data))
        lines.extend(_coverage_summary_events(data))
    else:
        # Legacy fallback
        lines.extend(_requirements_coverage(data))
        lines.extend(_section_traceability(data))
        lines.extend(_coverage_summary(data))

    return "\n".join(lines) + "\n"


def _requirements_coverage(data: ComplianceData) -> list[str]:
    """Requirements coverage matrix with links to specs and sections."""
    if not data.requirements:
        return []

    # Build section lookup for test counts
    section_lookup: dict[str, SectionInfo] = {s.name: s for s in data.sections}

    # E2E coverage per split (pragmatic: count flows from plan files)
    e2e_by_split = _collect_e2e_coverage_by_split(data.project_root)

    lines = [
        "## Requirements Coverage",
        "",
        "| Requirement | Title | Priority | Section(s) | Unit Tests | E2E Coverage | Status |",
        "|-------------|-------|----------|------------|------------|-------------|--------|",
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

            # Aggregate unit test counts from linked sections
            total_passed = 0
            total_tests = 0
            for sec_name in req.sections:
                sec = section_lookup.get(sec_name)
                if sec:
                    total_passed += sec.tests_passed
                    total_tests += sec.tests_total

            tests_cell = f"{total_passed}/{total_tests}" if total_tests > 0 else "—"

            # E2E coverage for this requirement's split
            split_e2e = e2e_by_split.get(req.split, {})
            e2e_flows = split_e2e.get("flows", 0)
            e2e_specs = split_e2e.get("specs", 0)
            has_e2e = e2e_specs > 0
            e2e_cell = f"Split: {e2e_specs} specs" if has_e2e else "—"

            # Status: 3-tier based on unit + E2E
            has_unit = total_tests > 0 and total_passed == total_tests
            if has_unit and has_e2e:
                status = "COVERED"
            elif has_unit:
                status = "PARTIAL"
            elif has_e2e:
                status = "E2E ONLY"
            elif total_tests > 0:
                status = "FAIL"
            else:
                status = "NO TESTS"
        else:
            sections_cell = "—"
            tests_cell = "—"
            e2e_cell = "—"
            status = "UNLINKED"

        lines.append(
            f"| {req_link} | {display_text} | {req.priority} "
            f"| {sections_cell} | {tests_cell} | {e2e_cell} | {status} |"
        )

    lines.append("")
    return lines


def _collect_e2e_coverage_by_split(project_root: Path) -> dict[str, dict]:
    """Count E2E flows and specs per split.

    Reads planning/*/claude-plan-e2e.md for planned flows and
    e2e/flows/*.spec.ts for existing specs.
    Returns: {"01-foundation": {"flows": 10, "specs": 7}, ...}
    """
    result: dict[str, dict] = {}

    # Count planned flows from E2E plan files
    planning_dir = project_root / "planning"
    if planning_dir.exists():
        for plan_file in planning_dir.glob("*/claude-plan-e2e.md"):
            split_name = plan_file.parent.name
            try:
                content = plan_file.read_text(encoding="utf-8")
                flows = len(re.findall(r"^### Flow \d+", content, re.MULTILINE))
            except OSError:
                flows = 0
            result.setdefault(split_name, {"flows": 0, "specs": 0})
            result[split_name]["flows"] = flows

    # Count existing spec files (NN-name.spec.ts → split NN)
    e2e_dir = project_root / "e2e" / "flows"
    if e2e_dir.exists():
        for spec_file in e2e_dir.glob("*.spec.ts"):
            # Extract split number from filename: 01-auth.spec.ts → "01"
            match = re.match(r"^(\d{2})-", spec_file.name)
            if match:
                prefix = match.group(1)
                # Find matching split name
                for split_name in result:
                    if split_name.startswith(prefix):
                        result[split_name]["specs"] += 1
                        break

    return result


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

    # E2E coverage
    e2e_by_split = _collect_e2e_coverage_by_split(data.project_root)
    splits_with_e2e = sum(1 for s in e2e_by_split.values() if s.get("specs", 0) > 0)
    total_e2e_specs = sum(s.get("specs", 0) for s in e2e_by_split.values())
    total_e2e_flows = sum(s.get("flows", 0) for s in e2e_by_split.values())
    lines.extend([
        f"| E2E specs | {total_e2e_specs} (across {splits_with_e2e} splits) |",
        f"| E2E planned flows | {total_e2e_flows} |",
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


# ---------------------------------------------------------------------------
# Event-based generation
# ---------------------------------------------------------------------------

def _requirements_coverage_events(data: ComplianceData) -> list[str]:
    """Requirements coverage from work events with Last Verified column."""
    if not data.requirements:
        return []

    # Build FR → events mapping
    fr_events: dict[str, list[WorkEvent]] = {}
    for we in data.work_events:
        for fr_id in we.affected_frs:
            fr_events.setdefault(fr_id, []).append(we)

    e2e_by_split = _collect_e2e_coverage_by_split(data.project_root)

    lines = [
        "## Requirements Coverage",
        "",
        "| Requirement | Title | Priority | Verified By | Tests | Last Verified | Status |",
        "|-------------|-------|----------|-------------|-------|---------------|--------|",
    ]

    for req in data.requirements:
        anchor = _make_anchor(req.id)
        req_link = f"[{req.id}](../{req.spec_path}#{anchor})"
        display_text = req.text[:60] + ("..." if len(req.text) > 60 else "")

        events = fr_events.get(req.id, [])
        if events:
            # Verified-by: section names for build, event IDs for iterate
            refs = []
            for we in events:
                if we.source == "build" and we.section:
                    refs.append(we.section)
                else:
                    refs.append(we.id)
            verified_cell = ", ".join(refs[:4])
            if len(refs) > 4:
                verified_cell += f" +{len(refs) - 4}"

            # Test progression: first → latest
            first_tests = f"{events[0].tests_passed}/{events[0].tests_total}"
            last_tests = f"{events[-1].tests_passed}/{events[-1].tests_total}"
            if first_tests != last_tests:
                tests_cell = f"{first_tests} → {last_tests}"
            else:
                tests_cell = last_tests

            # Last verified timestamp
            last_ts = events[-1].timestamp[:10]
            source_tag = "iter" if events[-1].source == "iterate" else "build"
            last_verified = f"{last_ts} ({source_tag})"

            # Status
            all_passing = all(we.tests_passed == we.tests_total and we.tests_total > 0 for we in events)
            has_tests = any(we.tests_total > 0 for we in events)
            if has_tests and all_passing:
                status = "COVERED"
            elif has_tests:
                status = "FAIL"
            else:
                status = "NO TESTS"
        else:
            verified_cell = "—"
            tests_cell = "—"
            last_verified = "—"
            status = "NOT VERIFIED"

        lines.append(
            f"| {req_link} | {display_text} | {req.priority} "
            f"| {verified_cell} | {tests_cell} | {last_verified} | {status} |"
        )

    lines.append("")
    return lines


def _verification_timeline(data: ComplianceData) -> list[str]:
    """Chronological timeline of all work events verifying requirements."""
    if not data.work_events:
        return []

    lines = [
        "## Verification Timeline",
        "",
        "| Event | Source | Type | FRs | Tests | Commit | Date |",
        "|-------|--------|------|-----|-------|--------|------|",
    ]

    for we in data.work_events:
        name = we.section if we.source == "build" else (we.description or we.id)
        source = we.source
        event_type = "section" if we.source == "build" else (we.intent or "change")
        frs = ", ".join(we.affected_frs[:3])
        if len(we.affected_frs) > 3:
            frs += f" +{len(we.affected_frs) - 3}"
        tests = f"{we.tests_passed}/{we.tests_total}" if we.tests_total > 0 else "—"
        commit = we.commit[:7] if we.commit else "—"
        date = we.timestamp[:10]

        lines.append(f"| {name} | {source} | {event_type} | {frs} | {tests} | {commit} | {date} |")

    lines.append("")
    return lines


def _coverage_summary_events(data: ComplianceData) -> list[str]:
    """Coverage summary from events."""
    lines = ["## Coverage Summary", ""]

    build_events = [we for we in data.work_events if we.source == "build"]
    iterate_events = [we for we in data.work_events if we.source == "iterate"]

    splits_seen = set(we.split for we in build_events if we.split)

    lines.extend([
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total splits built | {len(splits_seen)} |",
        f"| Build sections | {len(build_events)} |",
        f"| Iterate changes | {len(iterate_events)} |",
    ])

    # Requirements coverage
    if data.requirements:
        total_reqs = len(data.requirements)
        must_reqs = [r for r in data.requirements if r.priority == "Must"]
        verified = [r for r in data.requirements if r.sections]
        verified_must = [r for r in must_reqs if r.sections]

        lines.extend([
            f"| Requirements total | {total_reqs} |",
            f"| Requirements verified | {len(verified)}/{total_reqs} |",
            f"| Must-have verified | {len(verified_must)}/{len(must_reqs)} |",
        ])

        unverified = [r for r in data.requirements if not r.sections]
        if unverified:
            lines.extend(["", "### Not Verified", ""])
            for req in unverified:
                lines.append(f"- [{req.id}](../{req.spec_path}) ({req.priority}): {req.text[:80]}...")

    # Last test run
    if data.test_runs:
        latest = data.test_runs[-1]
        lines.append(f"| Last full test run | {latest.timestamp[:10]} (Unit: {latest.unit_passed}/{latest.unit_total}, E2E: {latest.e2e_passed}/{latest.e2e_total}) |")

    # E2E coverage
    e2e_by_split = _collect_e2e_coverage_by_split(data.project_root)
    total_e2e_specs = sum(s.get("specs", 0) for s in e2e_by_split.values())
    if total_e2e_specs:
        lines.append(f"| E2E specs | {total_e2e_specs} |")

    # Review findings from events
    total_findings = sum(we.review_findings for we in data.work_events)
    unresolved = sum(we.review_findings - we.review_fixed for we in data.work_events)
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

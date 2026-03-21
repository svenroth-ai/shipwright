"""Mermaid diagram string builders for compliance reports.

Each function returns a complete Mermaid code block (with fences) ready
to embed in Markdown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.lib.data_collector import CommitEntry, DependencyInfo, SectionInfo


# Phase status -> color mapping
_COLORS = {
    "complete": "#4CAF50",   # green
    "in_progress": "#FFC107",  # yellow
    "pending": "#9E9E9E",    # gray
}

_TEXT_COLORS = {
    "complete": "#fff",
    "in_progress": "#000",
    "pending": "#fff",
}


def pipeline_status_diagram(configs: dict[str, dict]) -> str:
    """Generate flowchart LR showing pipeline phase status with color coding."""
    phases = [
        ("P", "Project", "project"),
        ("PL", "Plan", "plan"),
        ("B", "Build", "build"),
        ("T", "Test", "test"),
        ("D", "Deploy", "deploy"),
        ("CL", "Changelog", "changelog"),
    ]

    lines = ["```mermaid", "flowchart LR"]

    # Determine status per phase
    run_config = configs.get("run", {})
    pipeline_status = run_config.get("status", "pending")
    current_step = run_config.get("current_step", "")

    for node_id, label, phase_key in phases:
        status = _get_phase_status(phase_key, current_step, pipeline_status, configs)
        status_label = status.upper().replace("_", " ")
        lines.append(f'    {node_id}["{label}<br/>{status_label}"]')

    # Add edges
    ids = [p[0] for p in phases]
    lines.append(f"    {' --> '.join(ids)}")

    # Add styles
    lines.append("")
    for node_id, _, phase_key in phases:
        status = _get_phase_status(phase_key, current_step, pipeline_status, configs)
        color = _COLORS.get(status, _COLORS["pending"])
        text_color = _TEXT_COLORS.get(status, _TEXT_COLORS["pending"])
        lines.append(f"    style {node_id} fill:{color},color:{text_color}")

    lines.append("```")
    return "\n".join(lines)


def _get_phase_status(
    phase: str,
    current_step: str,
    pipeline_status: str,
    configs: dict[str, dict],
) -> str:
    """Determine status of a pipeline phase."""
    if pipeline_status == "complete":
        return "complete"

    # Check if phase has a config with status
    config = configs.get(phase, {})
    if config.get("status") == "complete":
        return "complete"

    if phase == current_step:
        return "in_progress"

    # Phases before current are complete, after are pending
    phase_order = ["project", "plan", "build", "test", "deploy", "changelog"]
    try:
        current_idx = phase_order.index(current_step)
        phase_idx = phase_order.index(phase)
        if phase_idx < current_idx:
            return "complete"
    except ValueError:
        pass

    return "pending"


def traceability_flow_diagram(
    splits: list, sections: list
) -> str:
    """Generate flowchart TD showing splits → sections → test results."""
    lines = ["```mermaid", "flowchart TD"]

    if not splits and not sections:
        lines.append('    EMPTY["No traceability data available"]')
        lines.append("```")
        return "\n".join(lines)

    # Splits subgraph
    lines.append("    subgraph Splits")
    for s in splits:
        safe_id = s.name.replace("-", "_")
        lines.append(f'        S_{safe_id}["{s.name}"]')
    lines.append("    end")

    # Sections subgraph
    lines.append("    subgraph Sections")
    for sec in sections:
        safe_id = sec.name.replace("-", "_")
        lines.append(f'        SEC_{safe_id}["{sec.name}"]')
    lines.append("    end")

    # Tests subgraph
    lines.append("    subgraph Tests")
    for sec in sections:
        safe_id = sec.name.replace("-", "_")
        if sec.tests_total > 0:
            lines.append(f'        T_{safe_id}["{sec.tests_passed}/{sec.tests_total} passed"]')
        else:
            lines.append(f'        T_{safe_id}["pending"]')
    lines.append("    end")

    # Edges: splits -> sections
    for sec in sections:
        split_id = sec.split.replace("-", "_")
        sec_id = sec.name.replace("-", "_")
        lines.append(f"    S_{split_id} --> SEC_{sec_id}")

    # Edges: sections -> tests
    for sec in sections:
        sec_id = sec.name.replace("-", "_")
        lines.append(f"    SEC_{sec_id} --> T_{sec_id}")

    lines.append("```")
    return "\n".join(lines)


def commit_type_pie(commits: list[CommitEntry]) -> str:
    """Generate pie chart of commit type distribution."""
    if not commits:
        return "```mermaid\npie title Commit Types\n    \"no commits\" : 1\n```"

    type_counts: dict[str, int] = {}
    for c in commits:
        type_counts[c.type] = type_counts.get(c.type, 0) + 1

    lines = ["```mermaid", "pie title Commit Types"]
    for type_name, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f'    "{type_name}" : {count}')
    lines.append("```")
    return "\n".join(lines)


def license_pie(dependencies: list[DependencyInfo]) -> str:
    """Generate pie chart of license distribution."""
    if not dependencies:
        return "```mermaid\npie title License Distribution\n    \"no packages\" : 1\n```"

    license_counts: dict[str, int] = {}
    for d in dependencies:
        license_counts[d.license] = license_counts.get(d.license, 0) + 1

    lines = ["```mermaid", "pie title License Distribution"]
    for lic, count in sorted(license_counts.items(), key=lambda x: -x[1]):
        lines.append(f'    "{lic}" : {count}')
    lines.append("```")
    return "\n".join(lines)


def testing_pyramid_diagram(sections: list[SectionInfo]) -> str:
    """Generate a test pyramid showing coverage layers."""
    total_passed = sum(s.tests_passed for s in sections)
    total_tests = sum(s.tests_total for s in sections)
    reviewed = sum(1 for s in sections if s.review_findings >= 0)

    lines = [
        "```mermaid",
        "flowchart TD",
        f'    UNIT["Unit Tests<br/>{total_passed}/{total_tests} passed"]',
        f'    REVIEW["Code Review<br/>{reviewed} sections reviewed"]',
        '    SMOKE["Smoke Tests<br/>HTTP 200 check"]',
        '    E2E["E2E Tests<br/>Playwright"]',
        '    SEC["Security<br/>Aikido SAST/SCA"]',
        "",
        "    SEC --> E2E --> SMOKE --> REVIEW --> UNIT",
        "",
        "    style UNIT fill:#4CAF50,color:#fff",
        "    style REVIEW fill:#4CAF50,color:#fff",
        "    style SMOKE fill:#9E9E9E,color:#fff",
        "    style E2E fill:#9E9E9E,color:#fff",
        "    style SEC fill:#9E9E9E,color:#fff",
        "```",
    ]
    return "\n".join(lines)

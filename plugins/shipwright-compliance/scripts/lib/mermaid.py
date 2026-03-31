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


_DEFAULT_PIPELINE = ["project", "design", "plan", "build", "test", "changelog", "deploy"]


def _node_id(phase: str) -> str:
    """Generate a short Mermaid node ID from a phase name."""
    return phase.upper().replace("-", "_")[:8]


def pipeline_status_diagram(configs: dict[str, dict]) -> str:
    """Generate flowchart LR showing pipeline phase status with color coding."""
    run_config = configs.get("run", {})
    pipeline = run_config.get("pipeline", _DEFAULT_PIPELINE)
    phases = [(_node_id(p), p.replace("-", " ").title(), p) for p in pipeline]

    lines = ["```mermaid", "flowchart LR"]

    # Determine status per phase
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

    run_config = configs.get("run", {})

    # Explicit completed_steps takes priority
    completed_steps = run_config.get("completed_steps", [])
    if phase in completed_steps:
        return "complete"

    # Check if phase has a config with status
    config = configs.get(phase, {})
    if config.get("status") == "complete":
        return "complete"

    if phase == current_step:
        return "in_progress"

    # Phases before current are complete, after are pending
    phase_order = run_config.get("pipeline", _DEFAULT_PIPELINE)
    try:
        current_idx = phase_order.index(current_step)
        phase_idx = phase_order.index(phase)
        if phase_idx < current_idx:
            return "complete"
    except ValueError:
        pass

    return "pending"


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

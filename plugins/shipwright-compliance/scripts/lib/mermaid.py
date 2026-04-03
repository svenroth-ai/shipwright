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


def testing_pyramid_diagram(sections: list[SectionInfo], test_results=None) -> str:
    """Generate a test pyramid showing coverage layers with real data when available."""
    total_passed = sum(s.tests_passed for s in sections)
    total_tests = sum(s.tests_total for s in sections)
    reviewed = sum(1 for s in sections if s.review_findings >= 0)

    tr = test_results  # TestResults | None

    # Unit layer — always from section data
    unit_label = f"Unit Tests<br/>{total_passed}/{total_tests} passed"
    unit_color = "#4CAF50" if total_passed == total_tests and total_tests > 0 else "#F44336"

    # Review layer
    review_label = f"Code Review<br/>{reviewed} sections reviewed"
    review_color = "#4CAF50"

    # Smoke layer — from test_results if available
    if tr and tr.smoke_status:
        smoke_label = f"Smoke Tests<br/>{tr.smoke_status.upper()}"
        if tr.smoke_url:
            smoke_label += f" ({tr.smoke_url})"
        smoke_color = "#4CAF50" if tr.smoke_status in ("pass", "PASS") else "#F44336"
    else:
        smoke_label = "Smoke Tests<br/>not run"
        smoke_color = "#9E9E9E"

    # E2E layer — from test_results if available
    if tr and not tr.e2e_skipped and tr.e2e_total > 0:
        e2e_label = f"E2E Tests<br/>{tr.e2e_passed}/{tr.e2e_total} passed"
        e2e_color = "#4CAF50" if tr.e2e_passed == tr.e2e_total else "#FFC107"
    elif tr and tr.e2e_skipped:
        e2e_label = f"E2E Tests<br/>skipped"
        e2e_color = "#9E9E9E"
    else:
        e2e_label = "E2E Tests<br/>not run"
        e2e_color = "#9E9E9E"

    # Visual layer — from test_results if available
    if tr and not tr.visual_skipped and tr.visual_total > 0:
        vis_label = f"Visual<br/>{tr.visual_passed}/{tr.visual_total} screens"
        vis_color = "#4CAF50" if tr.visual_passed == tr.visual_total else "#FFC107"
    elif tr and tr.visual_skipped:
        vis_label = "Visual<br/>skipped"
        vis_color = "#9E9E9E"
    else:
        vis_label = "Visual<br/>not run"
        vis_color = "#9E9E9E"

    # Security layer — always informational
    sec_label = "Security<br/>Aikido SAST/SCA"
    sec_color = "#9E9E9E"

    lines = [
        "```mermaid",
        "flowchart TD",
        f'    UNIT["{unit_label}"]',
        f'    REVIEW["{review_label}"]',
        f'    SMOKE["{smoke_label}"]',
        f'    E2E["{e2e_label}"]',
        f'    VIS["{vis_label}"]',
        f'    SEC["{sec_label}"]',
        "",
        "    SEC --> VIS --> E2E --> SMOKE --> REVIEW --> UNIT",
        "",
        f"    style UNIT fill:{unit_color},color:#fff",
        f"    style REVIEW fill:{review_color},color:#fff",
        f"    style SMOKE fill:{smoke_color},color:#fff",
        f"    style E2E fill:{e2e_color},color:#fff",
        f"    style VIS fill:{vis_color},color:#fff",
        f"    style SEC fill:{sec_color},color:#fff",
        "```",
    ]
    return "\n".join(lines)

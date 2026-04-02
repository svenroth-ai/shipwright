#!/usr/bin/env python3
"""Generate agent_docs/build_dashboard.md from current pipeline and build state.

Reads shipwright_run_config.json and shipwright_build_config.json
to produce a human-readable progress dashboard.

Usage:
    uv run update_build_dashboard.py --project-root <path> [options]

Options:
    --phase <name>      Pipeline phase (project|design|plan|build|test|deploy|changelog)
    --section <name>    Current section being worked on
    --step <1-12>       Current step within the section
    --detail <text>     Free-text detail (e.g., "TDD green phase")
    --status <status>   Section status override (in_progress|complete|paused)
    --session-id <id>   Session ID for tracking

Writes to: agent_docs/build_dashboard.md
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add shared lib to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.config import collect_all_build_sections, read_config

STEP_LABELS = {
    1: "Read spec",
    2: "Install deps",
    3: "Write tests (red)",
    4: "Implement (green)",
    5: "Refactor",
    6: "Code review",
    7: "Apply fixes",
    8: "Commit",
    9: "Decision log",
    10: "Update state",
    11: "Handoff check",
    12: "Complete",
}

PIPELINE_PHASES = ["project", "design", "plan", "build", "test", "changelog", "deploy", "compliance"]


def format_status(section: dict, current_section: str | None, current_step: int | None, detail: str | None) -> str:
    """Format a section's status for the dashboard table."""
    name = section.get("name", "?")
    status = section.get("status", "pending")

    if name == current_section and current_step:
        label = STEP_LABELS.get(current_step, f"step {current_step}")
        return f"**step {current_step}/12 — {label}**"
    if status == "complete":
        return "complete"
    if status == "in_progress":
        return "in_progress"
    if status == "paused":
        return "paused"
    if status == "failed":
        return "FAILED"
    return "pending"


def _pipeline_status(run_config: dict, total_sections: int, completed_sections: int) -> str:
    """Format pipeline phase for the status column."""
    completed = set(run_config.get("completed_steps", []))
    current = run_config.get("current_step")

    # Detect split-loop: plan/build cycling with project+design already done
    # In this state, test/changelog/deploy haven't run for current cycle
    in_split_loop = (
        current in ("plan", "build")
        and "project" in completed
        and "design" in completed
    )

    def phase_status(phase: str) -> str:
        if in_split_loop and phase in ("test", "changelog", "deploy", "security"):
            return "pending"
        if phase in completed:
            return "complete"
        if phase == current:
            if phase == "build" and total_sections > 0:
                return f"**{completed_sections}/{total_sections} sections**"
            return "**in progress**"
        return "pending"

    return phase_status


def generate_pipeline_table(run_config: dict, total_sections: int, completed_sections: int) -> list[str]:
    """Generate the pipeline status table."""
    pipeline = run_config.get("pipeline", PIPELINE_PHASES)
    get_status = _pipeline_status(run_config, total_sections, completed_sections)

    lines = [
        "## Pipeline",
        "",
        "| Phase | Status |",
        "|-------|--------|",
    ]
    for phase in pipeline:
        status = get_status(phase)
        display = phase.capitalize()
        lines.append(f"| {display} | {status} |")
    lines.append("")

    # Validation issues (pending user decision)
    if run_config.get("status") == "needs_validation":
        for issue in run_config.get("validation_issues", []):
            lines.append(f"> **NEEDS DECISION — {issue.get('step', '?')}:** {issue.get('message', '')}")
        lines.append("")

    # Inform-level notes
    for note in run_config.get("validation_notes", []):
        lines.append(f"> **NOTE — {note.get('step', '?')}:** {note.get('message', '')}")
    if run_config.get("validation_notes"):
        lines.append("")

    return lines


def generate_dashboard(
    project_root: Path,
    phase: str | None = None,
    section: str | None = None,
    step: int | None = None,
    detail: str | None = None,
    status: str | None = None,
    session_id: str | None = None,
) -> str:
    """Generate dashboard markdown content."""
    run_config = read_config("run", project_root)
    build_info = collect_all_build_sections(project_root)

    # Current split sections (what the agent works on)
    sections = build_info["current"]
    total = len(sections)
    completed = sum(1 for s in sections if s.get("status") == "complete")

    # Total across all splits (for pipeline display)
    all_sections = build_info["all"]
    total_all = len(all_sections)
    completed_all = sum(1 for s in all_sections if s.get("status") == "complete")

    current_split = build_info["current_split"]
    completed_splits = build_info["completed_splits"]
    total_splits = build_info["total_splits"]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sid = session_id or os.environ.get("SHIPWRIGHT_SESSION_ID", "unknown")

    lines = [
        "# Shipwright Build Dashboard",
        f"> Updated: {now} | Session: {sid}",
        "",
    ]

    # Pipeline table (shown when run_config exists)
    if run_config:
        lines.extend(generate_pipeline_table(run_config, total_all, completed_all))

    # Phase detail line (e.g., "Last update (test): 833/833 unit passing")
    if phase and detail:
        lines.append(f"> **Last update ({phase}):** {detail}")
        lines.append("")

    # Section table — current split only
    split_label = ""
    if current_split:
        splits_done = len(completed_splits)
        # Count current split as done if all its sections are complete
        if total > 0 and completed == total:
            display_splits_done = splits_done + 1
        else:
            display_splits_done = splits_done
        split_label = f" — Split: {current_split} ({display_splits_done}/{total_splits} splits)"

    if total > 0:
        lines.append(f"## Build Sections ({completed}/{total} complete){split_label}")
    elif completed_splits and current_split and current_split not in completed_splits:
        # Split transition: current split awaiting plan, sections empty
        lines.append(f"## Build Sections{split_label}")
        lines.append("")
        lines.append(f"Split **{current_split}** — awaiting `/shipwright-plan`. "
                      f"Previous splits: {', '.join(completed_splits)} (archived).")
    elif sections is not None and run_config:
        lines.append(f"## Build Sections{split_label}")
    lines.append("")

    if sections:
        lines.append("| # | Section | Status | Commit |")
        lines.append("|---|---------|--------|--------|")
        for i, sec in enumerate(sections, 1):
            name = sec.get("name", "?")
            sec_status = format_status(sec, section, step, detail)
            commit = sec.get("commit", "--")
            lines.append(f"| {i} | {name} | {sec_status} | {commit} |")
        lines.append("")

    # Current activity
    if section:
        lines.append("## Current Activity")
        activity = f"Section: {section}"
        if step:
            label = STEP_LABELS.get(step, f"step {step}")
            activity += f" — {label}"
        if detail:
            activity += f" ({detail})"
        lines.append(activity)
        lines.append("")

    # Resume / status info
    next_section = None
    for sec in sections:
        if sec.get("status") not in ("complete",):
            next_section = sec.get("name")
            break

    split_done = total > 0 and completed == total
    all_done = split_done and (len(completed_splits) + 1 >= total_splits if total_splits > 0 else True)

    if status == "paused" or (completed < total and total > 0 and not section):
        lines.append("## Resume Info")
        if next_section:
            lines.append(f"Next: `/shipwright-run` (auto-resumes from {next_section})")
        else:
            lines.append("Next: `/shipwright-run`")
        lines.append("")
    elif split_done and all_done:
        lines.append("## Status")
        lines.append("All sections complete. Ready for `/shipwright-test`.")
        lines.append("")
    elif split_done and not all_done:
        lines.append("## Status")
        lines.append(f"Split {current_split} complete. Next: `/shipwright-run` to start next split.")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update build dashboard")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--phase", help="Pipeline phase that just completed")
    parser.add_argument("--section", help="Current section name")
    parser.add_argument("--step", type=int, choices=range(1, 13), help="Current step (1-12)")
    parser.add_argument("--detail", help="Free-text activity detail")
    parser.add_argument("--status", choices=["in_progress", "complete", "paused", "failed"])
    parser.add_argument("--session-id", help="Session ID")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()

    content = generate_dashboard(
        project_root,
        phase=args.phase,
        section=args.section,
        step=args.step,
        detail=args.detail,
        status=args.status,
        session_id=args.session_id,
    )

    agent_docs = project_root / "agent_docs"
    agent_docs.mkdir(exist_ok=True)
    (agent_docs / "build_dashboard.md").write_text(content, encoding="utf-8")

    print(json.dumps({
        "success": True,
        "dashboard": str(agent_docs / "build_dashboard.md"),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())

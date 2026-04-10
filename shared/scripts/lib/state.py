"""State management: checkpoint detection, resume logic.

Determines where a Shipwright session left off by reading config files
and checking filesystem artifacts. Used for recovery after context
compaction or /clear.
"""

from pathlib import Path
from typing import Any

from .config import read_all_configs


def detect_current_phase(project_root: str | Path) -> str:
    """Detect which SDLC phase the project is currently in.

    Returns one of: 'not_started', 'project', 'design', 'plan', 'build',
    'test', 'changelog', 'deploy', 'complete'.

    Two detection paths:
    1. Primary: orchestrator's current_step (when /shipwright-run is used)
    2. Fallback: heuristic from phase-specific configs (standalone invocation)
    """
    configs = read_all_configs(project_root)

    # Primary: use orchestrator's current_step (authoritative when present)
    run = configs["run"]
    if run:
        current = run.get("current_step")
        if current:
            return current
        # All pipeline steps completed
        pipeline = run.get("pipeline", [])
        completed = run.get("completed_steps", [])
        if pipeline and set(pipeline).issubset(set(completed)):
            return "complete"

    # Fallback: heuristic for standalone invocation (no run_config or
    # run_config without current_step). Check in-progress phases first,
    # then derive next step from completed phases.
    build = configs["build"]
    if build.get("sections"):
        sections = build["sections"]
        if any(s.get("status") != "complete" for s in sections):
            return "build"

    if configs["plan"].get("status") == "in_progress":
        return "plan"

    project = configs["project"]
    if project.get("design_phase") == "in_progress":
        return "design"

    if project.get("status") == "in_progress":
        return "project"

    # Completed phases: derive what comes next
    if configs["plan"].get("status") == "complete":
        return "build"

    if project.get("design_phase") == "complete":
        return "plan"

    if project.get("status") == "complete":
        return "design"

    return "not_started"


def get_checkpoint(project_root: str | Path) -> dict[str, Any]:
    """Get a checkpoint summary for session recovery.

    Returns a dict with phase, split, section, and status info
    that can be used to resume work.
    """
    configs = read_all_configs(project_root)
    phase = detect_current_phase(project_root)

    checkpoint: dict[str, Any] = {
        "phase": phase,
        "has_run_config": bool(configs["run"]),
        "has_project_config": bool(configs["project"]),
        "has_plan_config": bool(configs["plan"]),
        "has_build_config": bool(configs["build"]),
    }

    # Add split info if available
    run = configs["run"]
    project = configs["project"]
    if project.get("splits"):
        splits = project["splits"]
        # Use run_config.completed_splits (authoritative, maintained by orchestrator)
        # rather than project_config splits[].status (only written by /shipwright-project)
        completed_names = run.get("completed_splits", []) if run else []
        checkpoint["total_splits"] = len(splits)
        checkpoint["completed_splits"] = len(completed_names)
        checkpoint["current_split"] = next(
            (s["name"] for s in splits if s["name"] not in completed_names), None
        )

    # Add section info if available
    build = configs["build"]
    if build.get("sections"):
        sections = build["sections"]
        completed = [s for s in sections if s.get("status") == "complete"]
        checkpoint["total_sections"] = len(sections)
        checkpoint["completed_sections"] = len(completed)
        checkpoint["current_section"] = next(
            (s["name"] for s in sections if s.get("status") != "complete"), None
        )

    return checkpoint


def has_handoff(project_root: str | Path) -> bool:
    """Check if a session handoff file exists."""
    return (Path(project_root) / "agent_docs" / "session_handoff.md").exists()

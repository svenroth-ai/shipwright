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

    Returns one of: 'not_started', 'project', 'plan', 'build', 'test',
    'changelog', 'deploy', 'complete'.
    """
    configs = read_all_configs(project_root)

    if not configs["run"]:
        return "not_started"

    # Primary: use orchestrator's current_step (authoritative source)
    run = configs["run"]
    current = run.get("current_step")
    completed = run.get("completed_steps", [])
    if current:
        return current
    # All pipeline steps completed
    pipeline = run.get("pipeline", [])
    if pipeline and set(pipeline).issubset(set(completed)):
        return "complete"

    # Fallback: heuristic for projects without run_config.current_step
    build = configs["build"]
    if build.get("sections"):
        return "build"

    if configs["plan"].get("status") in ("in_progress", "complete"):
        return "plan"

    if configs["project"].get("status") in ("in_progress", "complete"):
        return "project"

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

"""State management: checkpoint detection, resume logic.

Determines where a Shipwright session left off by reading config files
and checking filesystem artifacts. Used for recovery after context
compaction or /clear.
"""

from pathlib import Path
from typing import Any

from .config import read_all_configs
from .handoff_phase_status import phase_tasks_progress as _phase_tasks_progress


def detect_current_phase(project_root: str | Path) -> str:
    """Detect which SDLC phase the project is currently in.

    Returns one of: 'not_started', 'project', 'design', 'plan', 'build',
    'test', 'changelog', 'deploy', 'complete'.

    Three detection paths, in order:
    1. Primary: phase_tasks[] (v2) — the orchestrator's per-phase task
       list, authoritative for progress within a driven (/shipwright-run)
       run.
    2. Secondary: the write-once ``current_step`` field, ONLY when
       phase_tasks[] gave no confident signal at all (a standalone/v1-only
       run, or an adopted-then-standalone repo whose established-at-
       adoption entries are all finished). ``current_step`` is stamped
       once at run creation (config_factory) and the v2 lifecycle never
       advances it, so a driven run always has a confident phase_tasks[]
       answer before this is reached — code review, campaign
       p4-04-retire-write-once-steps, sub-iterate s3: an earlier version of
       this migration dropped this path entirely, regressing every
       standalone run past ``build`` (whose config heuristic below cannot
       express test/changelog/deploy) to misreporting "build". Mirrors
       ``shared/scripts/hooks/generate_handoff_on_stop.py`` and
       ``suggest_iterate.py``'s identical fallback gate.
    3. Tertiary: heuristic from phase-specific configs (only when the run
       config itself has no usable ``current_step`` either, or there is no
       run_config at all).
    """
    configs = read_all_configs(project_root)

    run = configs["run"]
    if run:
        current, completed = _phase_tasks_progress(run)
        if current:
            return current
        pipeline = run.get("pipeline", [])
        if pipeline and completed and set(pipeline).issubset(completed):
            return "complete"

        current_step = run.get("current_step")
        if current_step:
            return current_step
        completed_steps = set(run.get("completed_steps", []))
        if pipeline and set(pipeline).issubset(completed_steps):
            return "complete"

    # Tertiary fallback: heuristic for a run_config with no usable
    # current_step either, or no run_config at all. Check in-progress
    # phases first, then derive next step from completed phases.
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
    return (Path(project_root) / ".shipwright" / "agent_docs" / "session_handoff.md").exists()

"""Build-progress aggregation for the orchestrator package.

Reads ``shipwright_build_config.json`` and returns section + split
progress. Used by the orchestrator autopilot loop, the build dashboard
renderer, and the resume-detection logic in SKILL.md.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def get_build_progress(project_root: Path) -> dict[str, Any]:
    """Return section-level progress for the build phase.

    Reads shipwright_build_config.json and returns counts plus the next
    section to work on.  Used by the orchestrator autopilot loop and the
    resume-detection logic in SKILL.md.

    Returns split-aware progress:
        split_done: all sections in current split are complete
        all_done: entire build is done (all splits complete)
    """
    from lib.config import collect_all_build_sections

    build_info = collect_all_build_sections(project_root)

    # Current split sections (what the agent works on)
    sections = build_info["current"]
    completed = [s for s in sections if s.get("status") == "complete"]
    in_progress = [s for s in sections if s.get("status") == "in_progress"]
    pending = [s for s in sections if s.get("status") not in ("complete", "in_progress", "failed")]

    # Next section: first in_progress (resume), else first pending
    next_section = None
    if in_progress:
        next_section = in_progress[0]
    elif pending:
        next_section = pending[0]

    # Split awareness
    split_done = len(sections) > 0 and len(completed) == len(sections)
    completed_splits = build_info["completed_splits"]
    total_splits = build_info["total_splits"]

    # all_done: split_done AND no more splits remain
    # For single-split projects (total_splits <= 1), split_done == all_done
    if total_splits > 0:
        all_done = split_done and (len(completed_splits) + 1 >= total_splits)
    else:
        all_done = split_done

    # Total across all splits (for dashboard reporting)
    all_sections = build_info["all"]
    total_all = len(all_sections)
    completed_all = sum(1 for s in all_sections if s.get("status") == "complete")

    return {
        "total": len(sections),
        "completed": len(completed),
        "in_progress": len(in_progress),
        "completed_sections": [s.get("name") for s in completed],
        "next_section": next_section.get("name") if next_section else None,
        "split_done": split_done,
        "all_done": all_done,
        "current_split": build_info["current_split"],
        "completed_splits": completed_splits,
        "total_splits": total_splits,
        "total_all": total_all,
        "completed_all": completed_all,
    }

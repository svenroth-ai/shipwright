"""Read-only phase-task lookups (extracted from ``phase_task_lifecycle``)."""
# Import only through ``phase_task_lifecycle`` (it puts this lib dir on sys.path first).
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from phase_task_core import _fail, _find_task, _ok, _read_config


def get_phase_task(project_root: Path, phase_task_id: str) -> dict[str, Any]:
    config = _read_config(project_root)
    task = _find_task(config, phase_task_id)
    if task is None:
        return _fail("not_found", message=f"phaseTaskId {phase_task_id} not in phase_tasks[]")
    return _ok(task)


def find_phase_task_by_session_uuid(
    project_root: Path, session_uuid: str,
) -> Optional[dict[str, Any]]:
    """Returns the phase_tasks[] entry whose sessionUuid matches, or None.

    Used by phase_session_start.py at SessionStart-time discovery.
    """
    try:
        config = _read_config(project_root)
    except FileNotFoundError:
        return None
    for t in config.get("phase_tasks", []):
        if t.get("sessionUuid") == session_uuid:
            return t
    return None


def validate_prerequisites(project_root: Path, phase_task_id: str) -> dict[str, Any]:
    """Fail-closed prerequisite check.

    All entries in task.prerequisites[] must have status in {done, skipped}.
    Returns ok=True with prereqs_status snapshot if all satisfied; otherwise
    ok=False with blockMessage listing the offending prereqs.
    """
    config = _read_config(project_root)
    task = _find_task(config, phase_task_id)
    if task is None:
        return _fail("not_found", message=f"phaseTaskId {phase_task_id} not in phase_tasks[]")

    prereq_ids: list[str] = list(task.get("prerequisites") or [])
    snapshot: list[dict[str, str]] = []
    blockers: list[str] = []
    for pid in prereq_ids:
        prereq = _find_task(config, pid)
        if prereq is None:
            snapshot.append({"phaseTaskId": pid, "status": "missing"})
            blockers.append(f"{pid}=missing")
            continue
        st = prereq.get("status", "unknown")
        snapshot.append({"phaseTaskId": pid, "status": st})
        if st not in {"done", "skipped"}:
            blockers.append(f"{pid}={st}")

    if blockers:
        return _fail(
            "prereqs_unmet",
            message=f"prerequisite(s) not terminal: {', '.join(blockers)}",
            prereqs_status=snapshot,
        )
    return _ok(task, prereqs_status=snapshot)

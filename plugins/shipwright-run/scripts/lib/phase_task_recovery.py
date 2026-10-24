"""Phase-task recovery (user escape hatch), extracted from ``phase_task_lifecycle``."""
# Import only through ``phase_task_lifecycle`` (it puts this lib dir on sys.path first).
from __future__ import annotations

from pathlib import Path
from typing import Any

from phase_task_core import (
    _PhaseTasksLock,
    _fail,
    _find_task,
    _guard_lock_timeout,
    _now_iso,
    _ok,
    _read_config,
    _write_config,
)


@_guard_lock_timeout
def recover_phase_task(
    project_root: Path,
    *,
    phase_task_id: str,
    force_status: str = "awaiting_launch",
) -> dict[str, Any]:
    """User-escape hatch: bumps version, clears ownership, resets status.

    Allowed force_status values: awaiting_launch | failed | skipped.
    After recover, any prior session holding the old version cannot
    complete or fail this task — version-CAS rejects it.

    If force_status == "awaiting_launch" and run was failed because of THIS
    task, run.status is reset to "in_progress" so the pipeline can resume.
    """
    if force_status not in {"awaiting_launch", "failed", "skipped"}:
        return _fail(
            "invalid_force_status",
            message=f"force_status must be one of awaiting_launch|failed|skipped, got {force_status!r}",
        )

    with _PhaseTasksLock(project_root):
        config = _read_config(project_root)
        task = _find_task(config, phase_task_id)
        if task is None:
            return _fail("not_found", message=f"phaseTaskId {phase_task_id} not in phase_tasks[]")

        old_status = task.get("status")
        old_version = int(task.get("version", 1))

        task["version"] = old_version + 1
        task["claimedBySessionUuid"] = None
        task["claimAttemptedAt"] = None
        task["status"] = force_status
        task["executionCount"] = int(task.get("executionCount", 0))  # NOT bumped — claim does that

        if force_status == "awaiting_launch":
            task["startedAt"] = None
            task["completedAt"] = None
            task["awaitingLaunchAt"] = _now_iso()
            # If run was failed because of this task, lift it back to in_progress
            if config.get("status") == "failed" and "failed" in (old_status or ""):
                config["status"] = "in_progress"
        else:
            # failed / skipped
            task["completedAt"] = _now_iso()
            # Track in completed_phase_task_ids if skipped (terminal)
            if force_status == "skipped":
                completed_ids = list(config.get("completed_phase_task_ids", []))
                if phase_task_id not in completed_ids:
                    completed_ids.append(phase_task_id)
                config["completed_phase_task_ids"] = completed_ids

        _write_config(project_root, config)
        return _ok(task, recovered_from=old_status, new_version=task["version"])

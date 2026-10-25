"""Phase-task recovery (user escape hatch) and re-dispatch fencing.

Extracted from ``phase_task_lifecycle``; that module re-exports both public functions.
"""
# Import only through ``phase_task_lifecycle`` (it puts this lib dir on sys.path first).
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from phase_task_core import (
    TERMINAL_STATUSES,
    _PhaseTasksLock,
    _fail,
    _find_task,
    _guard_lock_timeout,
    _now_iso,
    _ok,
    _read_config,
    _write_config,
)

# The stored skip reason is operator text that later readers (handoff, WebUI, agents) show:
# one line, no control characters, bounded.
MAX_SKIP_REASON_CHARS = 500
# Letters that render as blank (Hangul fillers): ``isalnum()`` is True for them.
_BLANK_LETTERS = frozenset("ᅟᅠㅤﾠ")


def _completion_unblocked(config: dict[str, Any]) -> bool:
    """True when a ``needs_validation`` run may now complete: the lifecycle's own
    run-completion invariant (``complete_phase_task``), re-checked after a skip.

    Only the lifecycle producer's pause is lifted — "pipeline-terminal task done while
    others were non-terminal". It writes no ``validation_issues``; the other producer
    (``step_planning.update_step``, v1 gate findings) always does, and a skip answers
    none of them, so any ``validation_issues`` key keeps the pause. The pipeline-terminal
    phase is ``deploy``, or ``changelog`` when ``deploy_target`` is ``"none"`` (the
    state machine's two ``None`` successors)."""
    if config.get("status") != "needs_validation" or "validation_issues" in config:
        return False
    tasks = config.get("phase_tasks") or []
    last = "changelog" if config.get("deploy_target") == "none" else "deploy"
    if not any(t.get("phase") == last and t.get("status") == "done" for t in tasks):
        return False
    return all(t.get("status") in TERMINAL_STATUSES for t in tasks)


def normalise_skip_reason(reason: Optional[str]) -> str:
    """The reason to store: control characters and line breaks become spaces, runs of
    whitespace collapse, the result is stripped and capped. ``""`` = no reason, and so is
    text without one visible letter or digit (bare punctuation, blank-rendering fillers
    such as U+3164 / U+2800)."""
    text = "".join(ch if ch.isprintable() else " " for ch in str(reason or ""))
    text = " ".join(text.split())[:MAX_SKIP_REASON_CHARS]
    return text if any(ch.isalnum() and ch not in _BLANK_LETTERS for ch in text) else ""


@_guard_lock_timeout
def recover_phase_task(
    project_root: Path,
    *,
    phase_task_id: str,
    force_status: str = "awaiting_launch",
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """User-escape hatch: bumps version, clears ownership, resets status.

    Allowed force_status values: awaiting_launch | failed | skipped.
    After recover, any prior session holding the old version cannot
    complete or fail this task — version-CAS rejects it.

    ``skipped`` REQUIRES a reason (blank or whitespace-only is refused
    ``skip_reason_required`` before anything is read or written): a skipped phase must
    say why afterwards; a reason with any other status is refused ``reason_only_for_skip``
    (nothing would record it). The normalised reason is stored as ``skipReason``. Every recover
    drops the task's earlier ``skipReason``, ``gate`` record and ``redispatchedAt`` first —
    they described a previous attempt the recover has just undone.

    If force_status == "awaiting_launch" and run was failed because of THIS
    task, run.status is reset to "in_progress" so the pipeline can resume.

    If force_status == "skipped" and the run sits in the lifecycle's ``needs_validation``
    (pipeline-terminal task done, others were open) and the skip leaves every task
    terminal, run.status becomes "complete" in the same write and the result carries
    ``run_status="complete"`` (``_completion_unblocked``). A ``failed`` recover never
    completes the run by itself; like ``complete_phase_task``, the invariant counts an
    already-``failed`` task as terminal, so a later skip of the last open task does. A
    skipped task's successors are not planned: skipping is the operator's call.
    """
    if force_status not in {"awaiting_launch", "failed", "skipped"}:
        return _fail(
            "invalid_force_status",
            message=f"force_status must be one of awaiting_launch|failed|skipped, got {force_status!r}",
        )
    if reason is not None and force_status != "skipped":
        return _fail(
            "reason_only_for_skip",
            message=(f"--reason is recorded only with --force-status skipped; drop it for "
                     f"{force_status!r} (nothing was changed)."),
        )
    skip_reason = normalise_skip_reason(reason)
    if force_status == "skipped" and not skip_reason:
        return _fail(
            "skip_reason_required",
            message=('--force-status skipped needs --reason "<why>" with at least one letter '
                     "or digit: a skipped phase must record why it was skipped (FR-01.01)."),
        )

    with _PhaseTasksLock(project_root):
        config = _read_config(project_root)
        task = _find_task(config, phase_task_id)
        if task is None:
            return _fail("not_found", message=f"phaseTaskId {phase_task_id} not in phase_tasks[]")

        old_status = task.get("status")
        old_version = int(task.get("version", 1))
        extra: dict[str, Any] = {}

        task["version"] = old_version + 1
        task["claimedBySessionUuid"] = None
        task["claimAttemptedAt"] = None
        task["status"] = force_status
        task["executionCount"] = int(task.get("executionCount", 0))  # NOT bumped — claim does that
        for stale_key in ("skipReason", "gate", "redispatchedAt"):
            task.pop(stale_key, None)

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
                task["skipReason"] = skip_reason
                completed_ids = list(config.get("completed_phase_task_ids", []))
                if phase_task_id not in completed_ids:
                    completed_ids.append(phase_task_id)
                config["completed_phase_task_ids"] = completed_ids
                # The skip may have been the last thing holding the run open: complete
                # it in THIS write (both or neither), as complete_phase_task would have.
                if _completion_unblocked(config):
                    config["status"] = extra["run_status"] = "complete"

        _write_config(project_root, config)
        return _ok(task, recovered_from=old_status, new_version=task["version"], **extra)


@_guard_lock_timeout
def redispatch_phase_task(
    project_root: Path,
    *,
    phase_task_id: str,
    session_uuid: str,
) -> dict[str, Any]:
    """Rotate the CAS ``version`` of a task that is dispatched again while ``in_progress``.

    A gate retry or a crash resume re-claims the SAME task with the same ``sessionUuid``;
    without a new ``version`` the earlier dispatch's phase-runner result would still pass
    the owner+version check. Bumping it under the lock fences that result off: its apply
    (ok or not) is refused ``stale_version``. ``executionCount`` is unchanged (the task is
    not re-run from scratch), the claim stays, ``redispatchedAt`` records when.
    ``startedAt`` is deliberately kept: the canon ``phase_history`` window
    (``gate_run_id``) still opens at the claim, so an entry the phase skill wrote during an
    earlier dispatch of this same claim still counts.

    A separate lock from ``claim_phase_task`` (fail-closed: a recover landing in between
    makes this refuse, and ``begin_dispatch`` then records no dispatch).
    """
    with _PhaseTasksLock(project_root):
        config = _read_config(project_root)
        task = _find_task(config, phase_task_id)
        if task is None:
            return _fail("not_found", message=f"phaseTaskId {phase_task_id} not in phase_tasks[]")
        if task.get("status") != "in_progress":
            return _fail("invalid_status",
                         message=f"Cannot re-dispatch from status {task.get('status')!r}.")
        if task.get("claimedBySessionUuid") != session_uuid:
            return _fail(
                "stale_session",
                message=(f"Task {phase_task_id} is claimed by "
                         f"{task.get('claimedBySessionUuid')!r}, not {session_uuid!r}."),
                claimed_by=task.get("claimedBySessionUuid"),
            )
        old_version = int(task.get("version", 1))
        task["version"] = old_version + 1
        task["redispatchedAt"] = _now_iso()
        _write_config(project_root, config)
        return _ok(task, rotated_from=old_version, new_version=task["version"])

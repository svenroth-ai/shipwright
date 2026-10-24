"""Phase-task lifecycle subcommands for the /shipwright-run pipeline.

Implements the CAS-protected
state transitions that the F3 hooks (phase_session_start, phase_user_prompt_validate,
phase_session_stop) and the recovery CLI invoke.

Public API (each function takes project_root + identifying args, returns a result
dict with ``ok`` flag and either ``phase_task`` or ``reason`` + ``blockMessage``):
    - claim_phase_task: CAS awaiting_launch -> in_progress with wrong-skill check.
    - complete_phase_task: owner+version-checked done with run-completion invariant.
    - mark_phase_failed: owner+version-checked failed transition.
    - recover_phase_task: bumps version, clears claim, resets status.
    - validate_prerequisites: returns prereq status snapshot, fail-closed.
    - freeze_splits: design-stop hook entry — writes splits_frozen + splitMode
      with design->project->none fallback chain.
    - plan_next_phase: thin wrapper over phase_state_machine.next_phase_task
      that materialises a new phase_tasks[] entry or finalises the run.

All mutating helpers acquire a per-project lock to make read-modify-write
atomic and version-monotonic.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Local lib imports — sibling modules live next to us
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The shared primitives and the extracted transition modules are re-exported:
# callers (and tests) import every name from here, unchanged.
# To monkeypatch a helper, patch the DEFINING module (phase_task_core / _planning /
# _recovery), not this facade: moved functions resolve their helpers in their own module.
from phase_task_core import (  # noqa: E402,F401
    CONFIG_NAME,
    PLUGIN_PHASE_MAP,
    TERMINAL_STATUSES,
    LockTimeout,
    _check_owner_version,
    _fail,
    _find_task,
    _guard_lock_timeout,
    _new_phase_task_id,
    _now_iso,
    _ok,
    _PhaseTasksLock,
    _read_config,
    _write_config,
)
from phase_task_lookup import (  # noqa: E402,F401
    find_phase_task_by_session_uuid,
    get_phase_task,
    validate_prerequisites,
)
from phase_task_planning import (  # noqa: E402,F401
    _normalise_splits,
    _plan_next_inplace,
    _resolve_splits_with_fallback,
    freeze_splits,
    plan_next_phase,
)
from phase_task_recovery import recover_phase_task  # noqa: E402,F401


# ---------------------------------------------------------------------------
# CAS transitions
# ---------------------------------------------------------------------------

@_guard_lock_timeout
def claim_phase_task(
    project_root: Path,
    *,
    phase_task_id: str,
    session_uuid: str,
    expected_phase: str,
) -> dict[str, Any]:
    """CAS awaiting_launch -> in_progress.

    Idempotent re-entry: same session may call again, returns ok no-op.
    Wrong-skill: expected_phase != task.phase -> fail-closed.
    Duplicate launch (different session, same UUID claimed): fail-closed.
    Terminal status: fail-closed (suggest recover-phase-task).
    """
    with _PhaseTasksLock(project_root):
        config = _read_config(project_root)
        task = _find_task(config, phase_task_id)
        if task is None:
            return _fail("not_found", message=f"phaseTaskId {phase_task_id} not in phase_tasks[]")

        if task["phase"] != expected_phase:
            return _fail(
                "wrong_skill",
                message=(
                    f"Session UUID claimed for phase '{task['phase']}' but launched "
                    f"under plugin for phase '{expected_phase}'. Either re-launch "
                    f"with the correct slash command, or call recover-phase-task "
                    f"to release the UUID."
                ),
                expected_phase=expected_phase,
                claimed_phase=task["phase"],
            )

        status = task.get("status")

        if status == "in_progress":
            if task.get("claimedBySessionUuid") == session_uuid:
                # Idempotent re-entry (e.g. SessionStart fired again on reconnect)
                return _ok(task, idempotent=True)
            return _fail(
                "duplicate_claim",
                message=(
                    f"Phase task {phase_task_id} is already claimed by another "
                    f"session ({task.get('claimedBySessionUuid')!r}). Duplicate launch detected."
                ),
            )

        if status in TERMINAL_STATUSES:
            return _fail(
                "phase_already_terminal",
                message=(
                    f"Phase task {phase_task_id} is in terminal status '{status}'. "
                    f"Use recover-phase-task to release it before re-launching."
                ),
            )

        if status not in {"awaiting_launch", "backlog"}:
            return _fail(
                "invalid_status",
                message=f"Cannot claim from status '{status}'.",
            )

        # CAS succeeds — flip to in_progress
        task["status"] = "in_progress"
        task["claimedBySessionUuid"] = session_uuid
        now = _now_iso()
        task["claimAttemptedAt"] = now
        task["startedAt"] = now
        task["executionCount"] = int(task.get("executionCount", 0)) + 1
        _write_config(project_root, config)
        return _ok(task)


@_guard_lock_timeout
def mark_phase_failed(
    project_root: Path,
    *,
    phase_task_id: str,
    session_uuid: str,
    expected_version: int,
    error: str,
) -> dict[str, Any]:
    """Owner+version-checked failure transition.

    Sets task.status=failed and run.status=failed. No next-phase planning.
    Stale-stop after recover (caller has stale version) -> fail-closed exit 2.
    """
    with _PhaseTasksLock(project_root):
        config = _read_config(project_root)
        task = _find_task(config, phase_task_id)
        if task is None:
            return _fail("not_found", message=f"phaseTaskId {phase_task_id} not in phase_tasks[]")

        check = _check_owner_version(task, session_uuid, expected_version)
        if check is not None:
            return check

        # Idempotent: already failed by this owner+version
        if task.get("status") == "failed":
            return _ok(task, idempotent=True)

        task["status"] = "failed"
        task["completedAt"] = _now_iso()
        errors = list(task.get("errors") or [])
        errors.append(error)
        task["errors"] = errors
        config["status"] = "failed"
        _write_config(project_root, config)
        return _ok(task, run_status="failed")


@_guard_lock_timeout
def complete_phase_task(
    project_root: Path,
    *,
    phase_task_id: str,
    session_uuid: str,
    expected_version: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Owner+version-checked terminal transition.

    If result.ok == False -> internally calls mark_phase_failed and returns.
    Else marks done, runs plan_next_phase to materialise the next task,
    or applies the run-completion invariant (deploy + ALL terminal -> complete,
    deploy + others non-terminal -> needs_validation).

    Idempotent: if status already done by this owner+version, no-op.
    """
    if not result.get("ok", False):
        # Failure branch — Plan v4 §phase_session_stop.py
        return mark_phase_failed(
            project_root,
            phase_task_id=phase_task_id,
            session_uuid=session_uuid,
            expected_version=expected_version,
            error=str(result.get("reason") or result.get("error") or "phase reported ok=false"),
        )

    with _PhaseTasksLock(project_root):
        config = _read_config(project_root)
        task = _find_task(config, phase_task_id)
        if task is None:
            return _fail("not_found", message=f"phaseTaskId {phase_task_id} not in phase_tasks[]")

        check = _check_owner_version(task, session_uuid, expected_version)
        if check is not None:
            return check

        if task.get("status") == "done":
            # Idempotent — already completed by this owner+version
            return _ok(task, idempotent=True)

        # Mark done
        task["status"] = "done"
        task["completedAt"] = _now_iso()
        task["result"] = result

        completed_ids = list(config.get("completed_phase_task_ids", []))
        if phase_task_id not in completed_ids:
            completed_ids.append(phase_task_id)
        config["completed_phase_task_ids"] = completed_ids

        # Plan next or apply run-completion invariant
        next_task = _plan_next_inplace(config, task)

        if next_task is None:
            # Pipeline-terminal — apply run-completion invariant
            non_terminal = [
                t for t in config["phase_tasks"]
                if t.get("status") not in TERMINAL_STATUSES
            ]
            if not non_terminal:
                config["status"] = "complete"
                _write_config(project_root, config)
                return _ok(task, run_status="complete", next_phase_task=None)
            config["status"] = "needs_validation"
            _write_config(project_root, config)
            return _ok(
                task,
                run_status="needs_validation",
                next_phase_task=None,
                pipeline_completion_blocked=[
                    {"phaseTaskId": t["phaseTaskId"], "status": t.get("status")}
                    for t in non_terminal
                ],
            )

        _write_config(project_root, config)
        return _ok(task, next_phase_task=next_task)

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

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Local lib imports — phase_state_machine lives next to us
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase_state_machine import (  # noqa: E402
    CompletedPhaseTask,
    NextPhaseSpec,
    next_phase_task,
)
from run_config_store import atomic_write_json  # noqa: E402

CONFIG_NAME = "shipwright_run_config.json"
LOCK_NAME = "shipwright_run_config.json.lock"

TERMINAL_STATUSES = frozenset({"done", "failed", "skipped"})

# Plugin-name -> phase mapping. Used by phase_session_start.py to know its
# own expected phase from CLAUDE_PLUGIN_ROOT. Centralised here so callers
# stay consistent.
PLUGIN_PHASE_MAP: dict[str, str] = {
    "shipwright-project": "project",
    "shipwright-design": "design",
    "shipwright-plan": "plan",
    "shipwright-build": "build",
    "shipwright-test": "test",
    "shipwright-security": "security",
    "shipwright-changelog": "changelog",
    "shipwright-deploy": "deploy",
}


# ---------------------------------------------------------------------------
# Cross-platform file lock (mirrors record_event.py:_FileLock pattern)
# ---------------------------------------------------------------------------

class _PhaseTasksLock:
    """Per-project lock for atomic phase_tasks[] mutations."""

    def __init__(self, project_root: Path):
        self._lock_path = project_root / LOCK_NAME
        self._fp = None

    def __enter__(self):
        self._fp = open(self._lock_path, "w", encoding="utf-8")
        if sys.platform == "win32":
            import msvcrt
            while True:
                try:
                    msvcrt.locking(self._fp.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.001)
        else:
            import fcntl
            fcntl.flock(self._fp, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self._fp:
            if sys.platform == "win32":
                import msvcrt
                try:
                    msvcrt.locking(self._fp.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                fcntl.flock(self._fp, fcntl.LOCK_UN)
            self._fp.close()


# ---------------------------------------------------------------------------
# Internal read/write helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_config(project_root: Path) -> dict[str, Any]:
    path = project_root / CONFIG_NAME
    if not path.exists():
        raise FileNotFoundError(f"{CONFIG_NAME} not found at {project_root}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_config(project_root: Path, config: dict[str, Any]) -> None:
    config["updated_at"] = _now_iso()
    atomic_write_json(project_root / CONFIG_NAME, config)  # atomic; readers never see a partial write (WP2/F12)


def _find_task(config: dict[str, Any], phase_task_id: str) -> Optional[dict[str, Any]]:
    for t in config.get("phase_tasks", []):
        if t.get("phaseTaskId") == phase_task_id:
            return t
    return None


def _ok(phase_task: dict[str, Any], **extras: Any) -> dict[str, Any]:
    out = {"ok": True, "phase_task": phase_task}
    out.update(extras)
    return out


def _fail(reason: str, *, message: str, **extras: Any) -> dict[str, Any]:
    out = {"ok": False, "reason": reason, "blockMessage": message}
    out.update(extras)
    return out


def _new_phase_task_id() -> str:
    return "ptk-" + uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Lookup / read-only helpers (no lock needed)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CAS transitions
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Splits freeze (design-stop hook)
# ---------------------------------------------------------------------------

def freeze_splits(project_root: Path) -> dict[str, Any]:
    """Freeze splits[] into run_config.splits_frozen + runConditions.splitMode.

    Authority chain (Plan v4 §Splits):
      1. shipwright_design_config.json.splits[] if parsable.
      2. shipwright_project_config.json.splits[] as fallback.
      3. splits_frozen=[], splitMode="none" if both missing/corrupt
         (records splits_frozen_with_fallback warning event).

    Empty splits list -> splitMode="none" (single-pass build).
    """
    splits, source, warning = _resolve_splits_with_fallback(project_root)

    with _PhaseTasksLock(project_root):
        config = _read_config(project_root)
        config["splits_frozen"] = splits
        rc = dict(config.get("runConditions") or {})
        rc["splitMode"] = "per_split" if splits else "none"
        config["runConditions"] = rc
        _write_config(project_root, config)

    return _ok(
        {"splits_frozen": splits, "splitMode": rc["splitMode"], "source": source},
        warning=warning,
    )


def _resolve_splits_with_fallback(project_root: Path) -> tuple[list[str], str, Optional[str]]:
    """Returns (splits, source, warning). Never raises."""
    for candidate, source in (
        (project_root / "shipwright_design_config.json", "design"),
        (project_root / "shipwright_project_config.json", "project"),
    ):
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        raw_splits = data.get("splits")
        if isinstance(raw_splits, list):
            normalised = _normalise_splits(raw_splits)
            return normalised, source, None
    # Both missing/corrupt -> fallback
    return [], "fallback_none", "neither design nor project config provided usable splits"


def _normalise_splits(raw: list[Any]) -> list[str]:
    """Coerce splits[] entries to plain strings (id or name).

    Tolerates both ['01-core', '02-ui'] and [{'name': '01-core'}, ...] shapes.
    """
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            if item:
                out.append(item)
        elif isinstance(item, dict):
            sid = item.get("id") or item.get("name") or item.get("split")
            if isinstance(sid, str) and sid:
                out.append(sid)
    return out


# ---------------------------------------------------------------------------
# Plan-next-phase wrapper around the state machine
# ---------------------------------------------------------------------------

def plan_next_phase(
    project_root: Path, *, completed_phase_task_id: str,
) -> dict[str, Any]:
    """Materialise the successor phase_tasks[] entry, or signal pipeline-terminal.

    Reads the predecessor task, asks state_machine.next_phase_task for the
    structural next step, then writes a new phase_tasks[] entry with
    pre-bound IDs. Idempotent: if a successor for this predecessor already
    exists in the queue (matches phase + splitId + prerequisites), returns
    that one without appending a duplicate.
    """
    with _PhaseTasksLock(project_root):
        config = _read_config(project_root)
        predecessor = _find_task(config, completed_phase_task_id)
        if predecessor is None:
            return _fail(
                "not_found",
                message=f"predecessor {completed_phase_task_id} not in phase_tasks[]",
            )
        next_task = _plan_next_inplace(config, predecessor)
        _write_config(project_root, config)

    if next_task is None:
        return _ok({"pipeline_terminal": True})
    return _ok(next_task)


def _plan_next_inplace(
    config: dict[str, Any], predecessor: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Compute and append the successor task to config['phase_tasks'].

    Returns the newly-appended dict, or an existing matching task (idempotent),
    or None if the pipeline is terminal. Mutates config in place — caller
    is responsible for writing the result back to disk.
    """
    completed: CompletedPhaseTask = {
        "phaseTaskId": predecessor["phaseTaskId"],
        "phase": predecessor["phase"],
        "splitId": predecessor.get("splitId"),
        "status": predecessor.get("status", "done"),
    }
    spec: Optional[NextPhaseSpec] = next_phase_task(
        run_conditions=config["runConditions"],
        splits_frozen=list(config.get("splits_frozen") or []),
        completed=completed,
    )
    if spec is None:
        return None

    # Idempotency: if a task with the same phase + splitId + this predecessor
    # in prerequisites already exists, return it instead of appending.
    for t in config.get("phase_tasks", []):
        if (t.get("phase") == spec["phase"]
                and t.get("splitId") == spec["splitId"]
                and predecessor["phaseTaskId"] in (t.get("prerequisites") or [])):
            return t

    now = _now_iso()
    new_task: dict[str, Any] = {
        "phaseTaskId": _new_phase_task_id(),
        "phase": spec["phase"],
        "splitId": spec["splitId"],
        "sessionUuid": str(uuid.uuid4()),
        "version": 1,
        "status": "awaiting_launch",
        "title": spec["titleSuffix"],
        "description": "",
        "slashCommand": spec["slashCommand"],
        "prerequisites": list(spec["prerequisites"]),
        "claimedBySessionUuid": None,
        "claimAttemptedAt": None,
        "executionCount": 0,
        "createdAt": now,
        "awaitingLaunchAt": now,
        "startedAt": None,
        "completedAt": None,
        "result": None,
        "errors": [],
    }
    config.setdefault("phase_tasks", []).append(new_task)
    return new_task


# ---------------------------------------------------------------------------
# Internal CAS check
# ---------------------------------------------------------------------------

def _check_owner_version(
    task: dict[str, Any], session_uuid: str, expected_version: int,
) -> Optional[dict[str, Any]]:
    """Validate caller owns the claim and the version is current.

    Returns None if OK. Returns a fail dict otherwise.
    Used by complete_phase_task and mark_phase_failed.
    """
    actual_version = int(task.get("version", 0))
    if actual_version != int(expected_version):
        return _fail(
            "stale_version",
            message=(
                f"Stale-session error: caller has version {expected_version} but "
                f"task {task['phaseTaskId']} is now at version {actual_version} "
                f"(another session has taken ownership via recover-phase-task)."
            ),
            actual_version=actual_version,
            expected_version=int(expected_version),
        )

    claimed_by = task.get("claimedBySessionUuid")
    if claimed_by != session_uuid:
        return _fail(
            "stale_session",
            message=(
                f"Stale-session error: task {task['phaseTaskId']} is claimed by "
                f"{claimed_by!r}, not {session_uuid!r}."
            ),
            claimed_by=claimed_by,
        )

    if task.get("status") != "in_progress":
        # Don't reject if already terminal-by-this-owner — caller checks idempotency
        # at the public function level. This guard catches truly bad state.
        if task.get("status") not in TERMINAL_STATUSES:
            return _fail(
                "invalid_status_for_completion",
                message=f"Cannot complete/fail from status {task.get('status')!r}.",
            )
    return None

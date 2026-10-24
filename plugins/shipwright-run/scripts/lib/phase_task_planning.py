"""Splits freeze and next-phase planning, extracted from ``phase_task_lifecycle``."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Optional

from phase_state_machine import (
    CompletedPhaseTask,
    NextPhaseSpec,
    next_phase_task,
)
from phase_task_core import (
    _PhaseTasksLock,
    _fail,
    _find_task,
    _guard_lock_timeout,
    _new_phase_task_id,
    _now_iso,
    _ok,
    _read_config,
    _write_config,
)


# ---------------------------------------------------------------------------
# Splits freeze (design-stop hook)
# ---------------------------------------------------------------------------

@_guard_lock_timeout
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

@_guard_lock_timeout
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
        completed=completed, deploy_enabled=config.get("deploy_target") != "none",
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

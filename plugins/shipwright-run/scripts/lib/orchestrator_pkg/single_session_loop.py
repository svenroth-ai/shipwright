"""Single-session orchestrator loop logic (Campaign 2026-07-07, SS3).

The in-conversation driver for ``single_session`` mode. Where ``multi_session``
runs each phase as its own external UUID-bound Claude session (advanced by the
``phase_session_stop`` hook), ``single_session`` drives every phase from ONE
master conversation: resolve the next phase task -> dispatch a phase-runner
subagent -> apply its result -> repeat, until the pipeline is terminal.

This module is the ORCHESTRATION GLUE and owns NO bespoke completion path: every
phase-task mutation goes through ``phase_task_lifecycle`` (claim / complete /
mark_failed / freeze_splits) — the exact helpers the ``multi_session`` Stop hook
uses. Its only extra state is the resumable loop pointer in
``single_session.loop_state`` (``.shipwright/run_loop_state.json``), which holds
no authoritative phase status. That is WHY the loop lives here in
``orchestrator_pkg`` and not in the ``single_session`` package: the SS1
lifecycle-reuse contract test forbids that package from calling a mutator, and
this loop's whole job is to call them (through the ONE lifecycle).

``single_session_cli`` adapts these functions to the ``single-session-next`` /
``single-session-apply`` CLI subcommands the master drives. Serial only in v1 —
the state machine fans plan/build out per split in order; no parallel path.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

# ``single_session`` is a PURE data package (contracts only, no mutators) — safe
# to import at module top. ``scripts/lib`` must be on the path for it; constants
# already inserts it, but we guard here too so this module is import-order safe.
_LOCAL_LIB = str(Path(__file__).resolve().parents[1])
if _LOCAL_LIB not in sys.path:
    sys.path.insert(0, _LOCAL_LIB)

from single_session.loop_state import (  # noqa: E402
    advance_pointer,
    init_loop_state,
    load_loop_state,
    record_dispatch,
    save_loop_state,
    set_status,
)
from single_session import observability as obs  # noqa: E402
from single_session.orchestrator_context import verify_artifacts_exist  # noqa: E402
from single_session.result_contract import validate_phase_runner_result  # noqa: E402

from .config_io import load_run_config  # noqa: E402
from .constants import LEGACY_FALLBACK_MODE, SCHEMA_VERSION  # noqa: E402

SINGLE_SESSION = "single_session"

# Frontier statuses the loop dispatches: awaiting_launch (fresh) or in_progress
# (a resumed dispatch — master crashed after claim, before apply). Terminal
# statuses are never dispatched.
_DISPATCHABLE_STATUSES = ("awaiting_launch", "in_progress")


def _lifecycle():
    """Lazy handle on the phase-task mutators (mirrors ``router``); keeps the CAS
    machinery out of the base orchestrator import until a subcommand runs."""
    import phase_task_lifecycle  # noqa: WPS433

    return phase_task_lifecycle


def _dispatch_descriptor(task: dict[str, Any]) -> dict[str, Any]:
    """Compact record the master needs to spawn a phase-runner subagent.
    ``version`` is the CAS token the matching ``single-session-apply`` must echo."""
    return {
        "phaseTaskId": task["phaseTaskId"],
        "phase": task["phase"],
        "splitId": task.get("splitId"),
        "sessionUuid": task["sessionUuid"],
        "version": int(task.get("version", 1)),
        "slashCommand": task.get("slashCommand"),
        "title": task.get("title"),
        "status": task.get("status"),
    }


def _task_ref(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "phaseTaskId": task.get("phaseTaskId"),
        "phase": task.get("phase"),
        "splitId": task.get("splitId"),
        "status": task.get("status"),
    }


def _frontier_task(tasks: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """First non-terminal task in serial order — the loop's dispatch frontier."""
    for t in tasks:
        if t.get("status") in _DISPATCHABLE_STATUSES:
            return t
    return None


def resolve_next_dispatch(project_root: Path) -> dict[str, Any]:
    """Read-only (``migrate=False`` — never mutates run_config). Decide the
    loop's next action. Returns one ``action``: ``no_config`` | ``wrong_mode`` |
    ``complete`` | ``failed`` (+ ``failed_tasks``) | ``needs_validation`` (+
    ``blocked``) | ``dispatch`` (+ ``dispatch`` descriptor) | ``blocked`` (non-
    terminal but nothing runnable)."""
    config = load_run_config(project_root, migrate=False)
    if not config or config.get("schemaVersion") != SCHEMA_VERSION:
        return {"action": "no_config"}

    mode = config.get("mode")
    if mode != SINGLE_SESSION:
        return {"action": "wrong_mode", "mode": mode or LEGACY_FALLBACK_MODE}

    status = config.get("status")
    tasks = config.get("phase_tasks", [])
    if status == "complete":
        return {"action": "complete"}
    if status == "failed":
        return {
            "action": "failed",
            "failed_tasks": [_task_ref(t) for t in tasks if t.get("status") == "failed"],
        }
    if status == "needs_validation":
        return {
            "action": "needs_validation",
            "blocked": [
                _task_ref(t) for t in tasks
                if t.get("status") not in ("done", "failed", "skipped")
            ],
        }

    frontier = _frontier_task(tasks)
    if frontier is None:
        return {"action": "blocked", "reason": "no_dispatchable_task"}
    return {"action": "dispatch", "dispatch": _dispatch_descriptor(frontier)}


def begin_dispatch(project_root: Path, *, phase_task_id: str) -> dict[str, Any]:
    """Claim the frontier task (lifecycle) + record a dispatch in loop_state.
    Idempotent: re-claiming an already-in_progress task by its own sessionUuid is
    a no-op ok (crash-resume)."""
    lc = _lifecycle()
    task_res = lc.get_phase_task(project_root, phase_task_id)
    if not task_res.get("ok"):
        return task_res
    task = task_res["phase_task"]

    claim = lc.claim_phase_task(
        project_root, phase_task_id=phase_task_id,
        session_uuid=task["sessionUuid"], expected_phase=task["phase"],
    )
    if not claim.get("ok"):
        return claim

    config = load_run_config(project_root, migrate=False)
    run_id = config.get("runId", "unknown-run")
    state = load_loop_state(project_root)
    if state is None or state.get("runId") != run_id:
        # Fresh run, or a stale loop-state from a PRIOR run in this dir — never attach a
        # new run to an old pointer (mirrors the recovery-path runId guard).
        state = init_loop_state(run_id, current_phase_task_id=phase_task_id)
    state = record_dispatch(state)
    save_loop_state(project_root, state)

    dispatch = _dispatch_descriptor(claim["phase_task"])
    obs.emit_dispatch(project_root, run_id=state["runId"], dispatch=dispatch,
                      attempt=state["attempt"], idempotent=claim.get("idempotent", False))
    return {"ok": True, "dispatch": dispatch, "attempt": state["attempt"],
            "idempotent": claim.get("idempotent", False)}


def next_dispatch(project_root: Path) -> dict[str, Any]:
    """``single-session-next`` core: resolve the frontier, claim it, record it.
    Terminal / guard actions pass straight through; only ``dispatch`` claims."""
    resolved = resolve_next_dispatch(project_root)
    if resolved.get("action") != "dispatch":
        return resolved
    began = begin_dispatch(project_root, phase_task_id=resolved["dispatch"]["phaseTaskId"])
    if not began.get("ok"):
        return {"action": "claim_failed", **began}
    return {
        "action": "dispatch",
        "dispatch": began["dispatch"],
        "attempt": began["attempt"],
        "idempotent": began["idempotent"],
    }


def apply_phase_result(
    project_root: Path,
    *,
    phase_task_id: str,
    session_uuid: str,
    expected_version: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    """``single-session-apply`` core: contract-validate, persistence-guard,
    complete, advance.

    (1) Validate the phase-runner RESULT CONTRACT — a malformed result never
    reaches the lifecycle (no mutation; master fixes + retries). (2) On-disk
    PERSISTENCE GUARD (SS4): an ``ok`` result may not CLAIM an artifact it did
    not write to disk — a missing claim is rejected fail-closed BEFORE any
    mutation, closing the section-writer silent-loss class at the loop level.
    (3) A design phase that completed ok freezes splits BEFORE completion so the
    design->plan successor sees ``splits_frozen`` (mirrors ``phase_session_stop``).
    (4) Route through ``complete_phase_task`` — ok=False strict-stops via
    ``mark_phase_failed`` (NO successor); ok=True marks done + plans the next.
    (5) Advance the loop pointer / stamp the terminal loop status."""
    errors = validate_phase_runner_result(result)
    if errors:
        return {"ok": False, "reason": "invalid_result", "errors": errors}

    lc = _lifecycle()
    task_res = lc.get_phase_task(project_root, phase_task_id)
    if not task_res.get("ok"):
        return task_res
    task = task_res["phase_task"]
    phase = task["phase"]

    # If this apply is already stale (task recovered/advanced by another actor —
    # version bumped or claim released), the artifact guard must NOT pre-empt the
    # lifecycle's authoritative CAS reason; let complete_phase_task report
    # stale_version / stale_session truthfully.
    cas_current = (
        int(task.get("version", 1)) == int(expected_version)
        and task.get("sessionUuid") == session_uuid
    )

    # A successful, current apply must have PERSISTED every artifact it claims.
    # Verify on disk before any mutation — a claimed-but-unwritten artifact is
    # the exact silent-loss failure SS4 exists to prevent. (After task-existence
    # so a bad phaseTaskId surfaces as not_found; skipped for a stale apply so the
    # CAS reason wins, and for ok=False strict-stops which needn't produce files.)
    if result.get("ok") and cas_current:
        missing = verify_artifacts_exist(project_root, result.get("artifacts", []))
        if missing:
            return {"ok": False, "reason": "artifacts_missing", "missing": missing}

    if phase == "design" and result.get("ok"):
        try:
            lc.freeze_splits(project_root)
        except Exception as exc:  # noqa: BLE001 — never crash the loop on freeze
            return {"ok": False, "reason": "freeze_splits_failed", "error": str(exc)}

    completion = lc.complete_phase_task(
        project_root,
        phase_task_id=phase_task_id,
        session_uuid=session_uuid,
        expected_version=expected_version,
        result=result,
    )
    if not completion.get("ok"):
        # CAS reject (stale) — surface verbatim; loop_state left untouched.
        return {"ok": False, "completion": completion, "reason": completion.get("reason")}

    _advance_loop_state(project_root, completed_phase_task_id=phase_task_id, completion=completion)
    return {
        "ok": True,
        "completion": completion,
        "run_status": completion.get("run_status"),
        "next": resolve_next_dispatch(project_root),
    }


def _advance_loop_state(
    project_root: Path, *, completed_phase_task_id: str, completion: dict[str, Any]
) -> None:
    """Move the resumable loop pointer to reflect a completed task. No-op if
    loop_state was never initialised (e.g. a direct apply in a unit test). Uses
    ONLY ``loop_state.*`` mutators — never touches run_config."""
    state = load_loop_state(project_root)
    if state is None:
        return
    if completion.get("idempotent"):
        # Double-apply of an already-done task changed nothing — don't null the pointer.
        return
    next_task = completion.get("next_phase_task")
    next_id = next_task.get("phaseTaskId") if isinstance(next_task, dict) else None
    state = advance_pointer(
        state, completed_phase_task_id=completed_phase_task_id, next_phase_task_id=next_id,
    )

    run_status = completion.get("run_status")
    pt = completion.get("phase_task", {})
    failed = run_status == "failed" or pt.get("status") == "failed"
    if failed:
        state = set_status(state, "failed")
    elif run_status == "complete":
        state = set_status(state, "complete")
    elif run_status == "needs_validation":
        state = set_status(state, "stopped")
    # else: the loop is still running — keep "running".
    save_loop_state(project_root, state)

    obs.emit_phase_result(
        project_root, run_id=state["runId"], phase_task_id=completed_phase_task_id,
        phase=pt.get("phase"), run_status=run_status, failed=failed,
        reason=(pt.get("errors") or [None])[-1],
    )

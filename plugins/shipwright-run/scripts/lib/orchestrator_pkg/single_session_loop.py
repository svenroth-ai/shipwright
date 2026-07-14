"""Single-session orchestrator loop — the DISPATCH half (Campaign 2026-07-07, SS3).

Resolve the frontier phase task, claim it, record the dispatch. The APPLY half
(validate the phase-runner result, persist-guard it, complete it, advance the pointer)
lives in ``single_session_apply`` and is re-exported from here.

The in-conversation driver for the pipeline, and since
iterate-2026-07-14-remove-multi-session the ONLY one: the master drives every
phase from ONE conversation — resolve the next phase task -> dispatch a
phase-runner subagent -> apply its result -> repeat, until the pipeline is
terminal. (The removed ``multi_session`` mode instead ran each phase as its own
external bound Claude session, advanced by a ``phase_session_stop`` hook, and so
stalled on any surface that cannot start one.)

This module is the ORCHESTRATION GLUE and owns NO bespoke completion path: every
phase-task mutation goes through ``phase_task_lifecycle`` (claim / complete /
mark_failed / freeze_splits) — the same helpers the removed Stop hook used, which
is why deleting that hook cost the pipeline nothing. Its only extra state is the
resumable loop pointer in
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
    init_loop_state,
    load_loop_state,
    record_dispatch,
    save_loop_state,
)
from single_session import observability as obs  # noqa: E402

from .config_io import (  # noqa: E402
    is_legacy_multi_session,
    is_single_session,
    load_run_config,
    mode_rejection,
)
from .constants import SCHEMA_VERSION  # noqa: E402

# The APPLY half lives in ``single_session_apply`` (split out when the drivability guard
# pushed this module past 300 LOC). Re-exported here because callers and tests reach it as
# ``single_session_loop.apply_phase_result``. ``_lifecycle`` is defined THERE and imported
# HERE — that direction keeps the two modules acyclic (apply imports nothing from this one
# at module level; it takes ``resolve_next_dispatch`` lazily at its single call site).
from .single_session_apply import _lifecycle, apply_phase_result  # noqa: E402,F401

SINGLE_SESSION = "single_session"

# Frontier statuses the loop dispatches: awaiting_launch (fresh) or in_progress
# (a resumed dispatch — master crashed after claim, before apply). Terminal
# statuses are never dispatched.
_DISPATCHABLE_STATUSES = ("awaiting_launch", "in_progress")


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
    loop's next action. Returns one ``action``: ``no_config`` | ``mode_unsupported``
    | ``complete`` | ``failed`` (+ ``failed_tasks``) | ``needs_validation`` (+
    ``blocked``) | ``dispatch`` (+ ``dispatch`` descriptor) | ``blocked`` (non-
    terminal but nothing runnable).

    The mode guard is the loop's FIRST gate, so a config that is not an explicit
    ``single_session`` run (a stale ``multi_session`` one, or a mode-less pre-SS1
    one) is refused here — before any claim, mutation or event.

    The EXPLICIT removed literal is caught BEFORE the schemaVersion check: whoever wrote
    it meant a pipeline, so a hand-edited config that lost its ``schemaVersion`` must get
    the migration message, not a misleading ``no_config`` (external review, GPT). The
    mode-LESS arm stays behind that check on purpose — a v1 / standalone config has no
    ``mode`` either, but it is not a pipeline run at all, and telling its owner to "set
    mode: single_session" would be nonsense."""
    config = load_run_config(project_root, migrate=False)
    if is_legacy_multi_session(config):
        return mode_rejection(config)
    if not config or config.get("schemaVersion") != SCHEMA_VERSION:
        return {"action": "no_config"}

    if not is_single_session(config):
        return mode_rejection(config)

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

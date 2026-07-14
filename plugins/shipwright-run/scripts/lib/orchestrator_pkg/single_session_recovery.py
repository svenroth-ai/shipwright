"""Single-session RESUME + RECOVERY + human-gate observability (Campaign 2026-07-07, SS5).

Recovery from a dead ``/shipwright-run`` orchestrator conversation, plus the
loop-state / observability side of the human-gate and the recover-phase-task escape.
These functions CALL a lifecycle mutator (``recover_phase_task``) and mutate
``loop_state``, so they live here in ``orchestrator_pkg`` alongside
``single_session_loop`` — the pure ``single_session`` package is forbidden from calling
a mutator (the SS1 lifecycle-reuse contract).

**Fail-closed gate.** EVERY entry point here first passes ``_guard``: it is a no-op
rejection (no file created, nothing mutated, no event) unless the run records the
explicit ``mode: single_session`` literal AND the persisted ``loop_state`` belongs to
the SAME run (``loop_state.runId == run_config.runId``). A config that is not a
drivable single-session run, or a stale loop-state left by a prior aborted run under a
newer run_config, is refused with ``mode_unsupported`` / ``runid_mismatch`` — never
silently attached to the wrong run.

**Why idempotent re-dispatch of an in_progress task is safe.** The phase-runner is a
SUBAGENT of the master conversation, so when the master dies the runner dies with it —
there is no orphaned live worker to race on resume. (Split-brain WAS a real concern
under the removed multi_session mode, whose phases ran as independent external Claude
processes that outlived the master; removing that mode removed the concern with it.)
Resume simply re-dispatches the in_progress task idempotently (``begin_dispatch``
re-claims by its own sessionUuid); the SS4 artifact persistence-guard still verifies
outputs on apply.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

# ``single_session`` is a pure data package; ``scripts/lib`` must be importable for it.
_LOCAL_LIB = str(Path(__file__).resolve().parents[1])
if _LOCAL_LIB not in sys.path:
    sys.path.insert(0, _LOCAL_LIB)

from single_session import observability as obs  # noqa: E402
from single_session.loop_state import (  # noqa: E402
    load_loop_state,
    save_loop_state,
    set_status,
)
from single_session.orchestrator_context import reload_orchestrator_context  # noqa: E402

from .config_io import load_run_config  # noqa: E402
from .config_io import is_single_session, mode_rejection  # noqa: E402
from .constants import SCHEMA_VERSION  # noqa: E402
from .single_session_loop import resolve_next_dispatch  # noqa: E402


def _lifecycle():
    """Lazy handle on the phase-task mutators (mirrors ``single_session_loop``)."""
    import phase_task_lifecycle  # noqa: WPS433

    return phase_task_lifecycle


def _guard(project_root: Path) -> dict[str, Any]:
    """Single-session + run-identity gate shared by every recovery entry point.

    ``ok=True`` (+ ``config``, ``run_id``, ``loop_state``) only for a single_session run
    whose persisted loop_state belongs to the same run. Otherwise ``ok=False`` with an
    ``action``: ``no_config`` | ``mode_unsupported`` | ``not_resumable`` (no loop_state
    yet) | ``runid_mismatch``. No file is created or mutated on any rejection.
    """
    config = load_run_config(project_root, migrate=False)
    if not config or config.get("schemaVersion") != SCHEMA_VERSION:
        return {"ok": False, "action": "no_config"}
    if not is_single_session(config):
        return mode_rejection(config)
    loop_state = load_loop_state(project_root)
    if loop_state is None:
        return {"ok": False, "action": "not_resumable", "reason": "no_loop_state"}
    run_id = config.get("runId")
    if loop_state.get("runId") != run_id:
        return {
            "ok": False,
            "action": "runid_mismatch",
            "config_run_id": run_id,
            "loop_state_run_id": loop_state.get("runId"),
        }
    return {"ok": True, "config": config, "run_id": run_id, "loop_state": loop_state}


def _guard_rejection(guard: dict[str, Any]) -> dict[str, Any]:
    """Public-facing subset of a failed guard (drops internal config/loop_state)."""
    return {k: v for k, v in guard.items() if k not in ("ok", "config", "loop_state", "run_id")}


def _loop_pointer(loop_state: dict[str, Any]) -> dict[str, Any]:
    """Compact loop-pointer fields for a card / event — identifiers only, no blobs
    (event-field whitelist: never serialise a full context/summary object)."""
    return {
        "status": loop_state.get("status"),
        "currentPhaseTaskId": loop_state.get("currentPhaseTaskId"),
        "lastCompletedPhaseTaskId": loop_state.get("lastCompletedPhaseTaskId"),
        "attempt": loop_state.get("attempt"),
    }


def resume_run(project_root: Path, *, confirm: bool = False) -> dict[str, Any]:
    """Resume decision for a dead single-session run.

    READ-ONLY by default (the confirm-card path): reads run_config + loop_state + the
    compact reload context and returns what resuming WOULD do — it neither claims a task
    nor emits. Emits the ``resume`` event ONLY when ``confirm=True`` (the user chose
    Resume); merely displaying the card records nothing (detection is not commitment).

    Actions: ``no_config`` | ``mode_unsupported`` | ``not_resumable`` | ``runid_mismatch`` |
    ``resume``. On ``resume`` it carries ``resumeAction`` (what ``single-session-next``
    will do next), the compact ``context`` (reload), the ``loopState`` pointer, and
    ``next`` — the resolved dispatch/terminal signal the master loops on after confirming.
    """
    guard = _guard(project_root)
    if not guard.get("ok"):
        return _guard_rejection(guard)

    loop_state = guard["loop_state"]
    run_id = guard["run_id"]
    resolved = resolve_next_dispatch(project_root)  # read-only
    context = reload_orchestrator_context(project_root)  # read-only, compact
    action = resolved.get("action")

    if action != "dispatch":
        # The run already finished / is blocked — nothing to re-dispatch. Surface the
        # real terminal signal (complete | failed | needs_validation | blocked) and emit
        # NOTHING (a finished run is not "resumed"; --confirm must not log a spurious event).
        return {
            "action": action,
            "loopState": _loop_pointer(loop_state),
            "context": context,
            "next": resolved,
        }

    if confirm:
        obs.emit(
            project_root, event_type="resume", run_id=run_id, resumeAction="dispatch",
            currentPhaseTaskId=loop_state.get("currentPhaseTaskId"),
            attempt=loop_state.get("attempt"),
        )
    return {
        "action": "resume",
        "resumeAction": "dispatch",
        "loopState": _loop_pointer(loop_state),
        "context": context,
        "next": resolved,
        "confirmed": confirm,
    }


def mark_human_gate(
    project_root: Path, *, phase_task_id: str, phase: str,
    paused: bool, split_id: Optional[str] = None,
) -> dict[str, Any]:
    """Record a human-gate PAUSE or RESUME on the loop pointer + emit the event.

    The master calls this when a phase pauses at an ``orchestrator-approve`` / ``hard-stop``
    gate (``paused=True``) and again when the human releases it (``paused=False``): it
    flips loop_state status ``paused_human_gate`` <-> ``running`` and emits
    ``human_gate_pause`` / ``human_gate_resume``. Mode- and run-identity-gated — a
    non-single-session or mismatched run is refused with no mutation and no event.
    """
    guard = _guard(project_root)
    if not guard.get("ok"):
        return {"ok": False, **_guard_rejection(guard)}

    loop_state = guard["loop_state"]
    run_id = guard["run_id"]
    new_status = "paused_human_gate" if paused else "running"
    loop_state = set_status(loop_state, new_status)
    save_loop_state(project_root, loop_state)

    obs.emit(
        project_root,
        event_type="human_gate_pause" if paused else "human_gate_resume",
        run_id=run_id, phaseTaskId=phase_task_id, phase=phase, splitId=split_id,
    )
    return {"ok": True, "status": new_status, "loopState": _loop_pointer(loop_state)}


def recover_single_session(
    project_root: Path, *, phase_task_id: str, force_status: str = "awaiting_launch",
) -> dict[str, Any]:
    """recover-phase-task INSIDE the single-session loop + loop-pointer realign + event.

    Reuses the generic lifecycle mutator verbatim (bumps version, clears the claim, resets
    status), then — only for a re-runnable ``awaiting_launch`` recovery — realigns the
    resumable loop pointer to the recovered task (attempt reset; loop status lifted back to
    ``running`` if the run had failed because of it), and emits a ``recovery`` event.
    Mode- and run-identity-gated. The generic ``recover-phase-task`` CLI is untouched for
    not a drivable single-session run.
    """
    guard = _guard(project_root)
    if not guard.get("ok"):
        return {"ok": False, **_guard_rejection(guard)}

    run_id = guard["run_id"]
    run_was_failed = guard["config"].get("status") == "failed"
    lc = _lifecycle()
    recovered = lc.recover_phase_task(
        project_root, phase_task_id=phase_task_id, force_status=force_status,
    )
    if not recovered.get("ok"):
        return {"ok": False, "reason": recovered.get("reason"), "recover": recovered}

    # Realign the loop pointer only for a re-runnable recovery (skipped/failed are terminal
    # — leave the pointer, the master resolves the next frontier via single-session-next).
    loop_state = load_loop_state(project_root)
    if loop_state is not None and force_status == "awaiting_launch":
        loop_state = {**loop_state, "currentPhaseTaskId": phase_task_id, "attempt": 0}
        # Lift the loop to running ONLY when recover actually cleared the run failure:
        # recover_phase_task lifts config.status off "failed" only when THIS task carried
        # the failure — recovering an unrelated task leaves the run failed, so the loop
        # pointer must not disagree with authoritative config.status.
        if run_was_failed and load_run_config(
            project_root, migrate=False
        ).get("status") != "failed":
            loop_state = set_status(loop_state, "running")
        save_loop_state(project_root, loop_state)

    obs.emit(
        project_root, event_type="recovery", run_id=run_id,
        phaseTaskId=phase_task_id, forceStatus=force_status,
        recoveredFrom=recovered.get("recovered_from"),
        newVersion=recovered.get("new_version"),
    )
    return {
        "ok": True,
        "recover": recovered,
        "loopState": _loop_pointer(loop_state) if loop_state else None,
    }

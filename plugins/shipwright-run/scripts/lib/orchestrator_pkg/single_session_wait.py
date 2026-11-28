"""A phase that WAITS for an outside event (U5, campaign dfp-changelog-followups).

A phase-runner result may carry ``waiting`` (``result_contract.WAITING_REASONS``; today only
``waiting_for_merge`` with the release PR's link): the phase is not done and not failed.
This module is the loop's whole handling of it, in three beats:

* **apply** (``apply_waiting``) — ``single-session-apply`` completes NOTHING: the task stays
  ``in_progress`` in run_config, no successor is planned (so deploy is not scheduled), the
  run status is unchanged. A ``waiting`` marker goes into the LOOP STATE, keyed to run id +
  phase task id + the task's CAS version (the ``gateTerminal`` pattern). A late result from
  an older dispatch is refused like a completion would be (``stale_version`` /
  ``stale_session``) and writes nothing.
* **next** (``waiting_action``) — while the marker is current, ``single-session-next``
  answers ``waiting`` (the link and what to do) instead of dispatching.
* **resume** (``release_waiting``) — a confirmed ``single-session-resume`` releases the
  marker (kept, flagged ``released``, so a replayed result of that same dispatch is refused
  ``stale_version`` instead of re-holding); ``single-session-next`` then re-dispatches the
  SAME task (rotating its version, which makes the marker stale).

No run_config schema value is involved. Losing the loop state only loses the hold: the task
is re-dispatched, and a phase that reports waiting checks the outside state itself on a
re-run (the result contract's rule), reporting ``waiting`` again or ``ok``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_LOCAL_LIB = str(Path(__file__).resolve().parents[1])
if _LOCAL_LIB not in sys.path:
    sys.path.insert(0, _LOCAL_LIB)

from single_session import observability as obs  # noqa: E402
from single_session.loop_state import (  # noqa: E402
    clear_waiting,
    init_loop_state,
    load_loop_state,
    record_waiting,
    save_loop_state,
    waiting_for,
    waiting_released_for,
)


def _lifecycle():
    import phase_task_lifecycle  # noqa: WPS433

    return phase_task_lifecycle


def apply_waiting(
    project_root: Path, config: dict[str, Any], task: dict[str, Any], *,
    session_uuid: str, expected_version: int, result: dict[str, Any],
) -> dict[str, Any]:
    """Hold ``task`` for the outside event in ``result["waiting"]`` (already contract-valid).

    Same refusals as a completion, checked first, so nothing is written for them:
    ``stale_version`` / ``stale_session`` (exit 2 at the CLI) and
    ``invalid_status_for_completion`` for a task that is no longer ``in_progress``."""
    version = _lifecycle().task_version(task)
    if version != int(expected_version):
        return {"ok": False, "reason": "stale_version",
                "current_version": version, "expected_version": int(expected_version)}
    if task.get("sessionUuid") != session_uuid:
        return {"ok": False, "reason": "stale_session"}
    if task.get("status") != "in_progress":
        return {"ok": False, "reason": "invalid_status_for_completion",
                "status": task.get("status")}
    try:
        state = load_loop_state(project_root)
    except (OSError, ValueError) as exc:
        # Fail closed: an unrecorded hold would let single-session-next re-dispatch at once.
        return {"ok": False, "reason": "loop_state_unreadable", "error": str(exc)}
    run_id = config.get("runId")
    phase_task_id = task["phaseTaskId"]
    if waiting_released_for(state, run_id=run_id, phase_task_id=phase_task_id, version=version):
        return {"ok": False, "reason": "stale_version",
                "detail": "Resume released this dispatch's hold: apply only the result of "
                          "the next single-session-next dispatch."}
    if not isinstance(state, dict) or state.get("runId") != run_id:
        state = init_loop_state(run_id, current_phase_task_id=phase_task_id)
    waiting = result["waiting"]
    state = record_waiting({**state, "currentPhaseTaskId": phase_task_id},
                           phase_task_id=phase_task_id, version=version,
                           reason=waiting["reason"], pr_url=waiting["pr_url"])
    save_loop_state(project_root, state)
    obs.emit(project_root, event_type="phase_waiting", run_id=run_id,
             phaseTaskId=phase_task_id, phase=task.get("phase"), reason=waiting["reason"])

    from .single_session_loop import resolve_next_dispatch  # lazy: the loop imports us

    return {"ok": True, "waiting": {"reason": waiting["reason"], "pr_url": waiting["pr_url"]},
            "run_status": config.get("status"), "next": resolve_next_dispatch(project_root)}


def next_step_text(phase: Any, reason: str, pr_url: str) -> str:
    """What the operator does next — plain words, the link as data."""
    if reason == "waiting_for_merge":
        return (f"Merge the pull request {pr_url} on the code host. Then re-invoke "
                f"/shipwright-run and choose Resume: the {phase} phase runs again and finishes.")
    return f"Then re-invoke /shipwright-run and choose Resume: the {phase} phase runs again."


def card_block(action: dict[str, Any]) -> dict[str, Any]:
    """The stable ``waiting`` block of a resume card (confirmed or not)."""
    return {k: action.get(k) for k in ("reason", "pr_url", "task", "next_step")}


def waiting_action(
    project_root: Path, config: dict[str, Any], frontier: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """The ``waiting`` answer while the frontier task's current version is held; else None.
    Read-only. An unreadable loop state is None (``begin_dispatch`` then reports it)."""
    try:
        state = load_loop_state(project_root)
    except (OSError, ValueError):
        return None
    marker = waiting_for(state, run_id=config.get("runId"),
                         phase_task_id=frontier.get("phaseTaskId"),
                         version=_lifecycle().task_version(frontier))
    if marker is None:
        return None
    phase = frontier.get("phase")
    return {"action": "waiting", "reason": marker.get("reason"), "pr_url": marker.get("prUrl"),
            "task": {"phaseTaskId": frontier.get("phaseTaskId"), "phase": phase,
                     "splitId": frontier.get("splitId"), "status": frontier.get("status")},
            "version": marker["version"],
            "next_step": next_step_text(phase, str(marker.get("reason")),
                                        str(marker.get("prUrl")))}


def release_waiting(project_root: Path, loop_state: dict[str, Any]) -> dict[str, Any]:
    """The operator confirmed Resume on a waiting run: release the hold so the next
    ``single-session-next`` dispatches the same task again. Returns the saved state."""
    state = clear_waiting(loop_state)
    save_loop_state(project_root, state)
    return state

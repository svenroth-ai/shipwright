"""Single-session orchestrator LOOP-STATE persistence (SS1 scaffold).

Resumability is a first-class reconciled-target foundation (#1): if the
``/shipwright-run`` master conversation dies mid single-session run, the loop is
resumed from THIS file + ``shipwright_run_config.json``.

Loop-state holds ONLY the orchestrator's own pointers/counters — which phase
task it is currently dispatching, the retry attempt, and the last completed
task. The AUTHORITATIVE per-phase status lives in ``run_config.phase_tasks[]``
and is mutated ONLY through ``phase_task_lifecycle``. This module NEVER reads or
writes ``shipwright_run_config.json``: no parallel completion path, no direct
run_config mutation (the SS1 lifecycle-reuse contract). It persists to
``.shipwright/run_loop_state.json`` — deliberately distinct from the campaign
autonomous loop's ``.shipwright/loop_state.json``.

The mutators are pure: each returns a NEW dict rather than editing in place, so
a caller can compute the next state, persist it, and keep the prior one for an
observability event.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# The shared durable atomic-write primitive (tmp + fsync + os.replace). ``shared``
# is a sibling of ``plugins`` in both the dev repo and the runtime plugin cache;
# this file sits at lib/single_session/, so the repo root is parents[5] (same
# offset orchestrator_pkg/constants.py relies on).
_SHARED_LIB = Path(__file__).resolve().parents[5] / "shared" / "scripts" / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from atomic_write import durable_atomic_write  # noqa: E402

LOOP_STATE_SCHEMA_VERSION = 1
LOOP_STATE_REL_PATH = Path(".shipwright") / "run_loop_state.json"

# Orchestrator lifecycle status — distinct from run_config.status and from a
# phase_task's status. Observability foundation (#7): SS5 emits structured
# events on these transitions (dispatch, human-gate pause/resume, strict-stop,
# recovery).
LOOP_STATUSES = ("running", "paused_human_gate", "stopped", "complete", "failed")


def loop_state_path(project_root: Path) -> Path:
    """Canonical loop-state path for a project."""
    return Path(project_root) / LOOP_STATE_REL_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_loop_state(
    run_id: str, *, current_phase_task_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a fresh loop-state for ``run_id``.

    ``runId`` ties the loop-state to the run config; ``currentPhaseTaskId`` is
    the phase task the orchestrator will dispatch first (the seed project task).
    """
    now = _now_iso()
    return {
        "schemaVersion": LOOP_STATE_SCHEMA_VERSION,
        "runId": run_id,
        "currentPhaseTaskId": current_phase_task_id,
        "attempt": 0,
        "lastCompletedPhaseTaskId": None,
        "status": "running",
        "createdAt": now,
        "updatedAt": now,
    }


def load_loop_state(project_root: Path) -> Optional[dict[str, Any]]:
    """Return the persisted loop-state, or None if it doesn't exist yet."""
    path = loop_state_path(project_root)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_loop_state(project_root: Path, state: dict[str, Any]) -> None:
    """Persist ``state`` atomically to ``.shipwright/run_loop_state.json``.

    Stamps ``updatedAt`` and ensures the ``.shipwright/`` directory exists. The
    write is tmp + fsync + os.replace, so a resuming reader never observes a
    half-written file. Writes ONLY the loop-state file — never run_config.
    """
    path = loop_state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    to_write = {**state, "updatedAt": _now_iso()}
    durable_atomic_write(path, json.dumps(to_write, indent=2) + "\n")


def record_dispatch(state: dict[str, Any]) -> dict[str, Any]:
    """Return a new state with the dispatch ``attempt`` incremented.

    Called each time the orchestrator (re)dispatches the current phase task to a
    phase-runner subagent — the counter bounds retries and feeds observability.
    """
    return {**state, "attempt": int(state.get("attempt", 0)) + 1}


def advance_pointer(
    state: dict[str, Any],
    *,
    completed_phase_task_id: str,
    next_phase_task_id: Optional[str],
) -> dict[str, Any]:
    """Return a new state advanced to the next phase task.

    Records ``completed_phase_task_id`` as the last completed task, points
    ``currentPhaseTaskId`` at the successor (None at pipeline-terminal), and
    resets ``attempt`` to 0 for the fresh task. This only moves the
    orchestrator's POINTER — the completed/next tasks' authoritative status was
    already set by ``phase_task_lifecycle``.
    """
    return {
        **state,
        "lastCompletedPhaseTaskId": completed_phase_task_id,
        "currentPhaseTaskId": next_phase_task_id,
        "attempt": 0,
    }


def set_status(state: dict[str, Any], status: str) -> dict[str, Any]:
    """Return a new state with ``status`` set (validated against LOOP_STATUSES)."""
    if status not in LOOP_STATUSES:
        raise ValueError(
            f"invalid loop status {status!r}; expected one of {', '.join(LOOP_STATUSES)}"
        )
    return {**state, "status": status}

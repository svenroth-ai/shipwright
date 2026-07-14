"""The APPLY half of the single-session orchestrator loop.

Split out of ``single_session_loop`` when the drivability guard pushed that module
past the 300-LOC limit. The seam is the loop's own two beats: ``single_session_loop``
owns DISPATCH (resolve the frontier, claim it, record it), and this module owns APPLY
(validate the phase-runner's result, persist-guard it, complete it, advance the pointer).

Like the dispatch half, this owns NO bespoke completion path: every phase-task mutation
goes through ``phase_task_lifecycle`` — the same helpers the deleted ``phase_session_stop``
hook called (iterate-2026-07-14-remove-multi-session), which is why removing that hook
cost the pipeline nothing.

Import direction: this module must NOT import ``single_session_loop`` at module level —
the loop re-exports ``apply_phase_result`` (many callers and tests reach it as
``single_session_loop.apply_phase_result``), so a top-level import here would be a cycle.
The one thing apply needs from the loop, ``resolve_next_dispatch``, is imported lazily at
its single call site.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# ``single_session`` is a PURE data package (contracts only, no mutators) — safe to
# import at module top. ``scripts/lib`` must be on the path for it; ``constants``
# already inserts it, but guard here too so this module is import-order safe.
_LOCAL_LIB = str(Path(__file__).resolve().parents[1])
if _LOCAL_LIB not in sys.path:
    sys.path.insert(0, _LOCAL_LIB)

from single_session import observability as obs  # noqa: E402
from single_session.loop_state import (  # noqa: E402
    advance_pointer,
    load_loop_state,
    save_loop_state,
    set_status,
)
from single_session.orchestrator_context import verify_artifacts_exist  # noqa: E402
from single_session.result_contract import validate_phase_runner_result  # noqa: E402

from .config_io import is_single_session, load_run_config, mode_rejection  # noqa: E402


def _lifecycle():
    """Lazy handle on the phase-task mutators (mirrors ``router``); keeps the CAS
    machinery out of the base orchestrator import until a subcommand runs.

    Lives here rather than in ``single_session_loop`` so the loop can import it from
    this module without either side importing the other at module level.
    """
    import phase_task_lifecycle  # noqa: WPS433

    return phase_task_lifecycle


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


def apply_phase_result(
    project_root: Path,
    *,
    phase_task_id: str,
    session_uuid: str,
    expected_version: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    """``single-session-apply`` core: guard, contract-validate, persistence-guard,
    complete, advance.

    (0) FIRST: the DRIVABILITY guard. ``apply`` is the loop's most destructive entry
    point — it completes a phase task, plans its successor, can flip ``run.status`` to
    terminal, and appends a durable ``phase_completed`` to the TRACKED events log. So it
    needs the same guard as ``next``: a config that is not an explicit ``single_session``
    run is refused here too, before the result is even validated. (Guarding only ``next``
    would have been theatre — the master resolves a dispatch once, then applies against
    whatever is on disk.)
    (1) Validate the phase-runner RESULT CONTRACT — a malformed result never reaches the
    lifecycle (no mutation; master fixes + retries).
    (2) On-disk PERSISTENCE GUARD (SS4): an ``ok`` result may not CLAIM an artifact it did
    not write to disk — a missing claim is rejected fail-closed BEFORE any mutation,
    closing the section-writer silent-loss class at the loop level.
    (3) A design phase that completed ok freezes splits BEFORE completion, so the
    design->plan successor sees ``splits_frozen`` and build fans out per split.
    (4) Route through ``complete_phase_task`` — ok=False strict-stops via
    ``mark_phase_failed`` (NO successor); ok=True marks done + plans the next.
    (5) Advance the loop pointer / stamp the terminal loop status.
    """
    config = load_run_config(project_root, migrate=False)
    if not is_single_session(config):
        return mode_rejection(config)

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

    # Lazy: the loop re-exports this function, so importing it at module level would
    # close an import cycle. By call time ``single_session_loop`` is fully loaded.
    from .single_session_loop import resolve_next_dispatch

    return {
        "ok": True,
        "completion": completion,
        "run_status": completion.get("run_status"),
        "next": resolve_next_dispatch(project_root),
    }

"""CLI adapter for the single-session orchestrator loop (Campaign 2026-07-07, SS3).

Maps the two subcommands the ``single_session`` master drives to the pure loop
functions in ``single_session_loop``:

  * ``single-session-next``  — resolve + claim + record the frontier phase task,
    or return a terminal signal (``complete`` / ``failed`` / ``needs_validation``).
  * ``single-session-apply`` — validate the phase-runner RESULT CONTRACT (read
    from ``--result-json``) and route it through the lifecycle.

Exit-code map (shared with ``router.dispatch_lifecycle``):
    0 -> dispatch / terminal signal / successful apply
    2 -> fail-closed CAS reject on apply (stale_version / stale_session)
    1 -> guard (wrong_mode / no_config), claim failure, invalid result, IO error
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SINGLE_SESSION_COMMANDS: frozenset[str] = frozenset(
    {
        "single-session-next", "single-session-apply", "single-session-reload",
        # SS5 resumability / recovery / human-gate observability.
        "single-session-resume", "single-session-gate", "single-session-recover",
    }
)

# CAS-reject reasons that map to a fail-closed apply exit code (mirrors router).
_FAIL_CLOSED_REASONS = frozenset(
    {"stale_version", "stale_session", "invalid_status_for_completion"}
)

# Terminal / dispatch signals that are a successful `next` outcome (exit 0).
_OK_NEXT_ACTIONS = ("dispatch", "complete", "failed", "needs_validation")


def dispatch_single_session(args: argparse.Namespace, project_root: Path) -> int:
    """Run a single-session subcommand; return the process exit code."""
    # Lazy import keeps the base orchestrator surface free of the loop module
    # (and, transitively, the CAS machinery) until a subcommand actually runs.
    from .single_session_loop import apply_phase_result, next_dispatch

    if args.command == "single-session-next":
        result = next_dispatch(project_root)
        # Durable phase_started at phase entry (B1/M-Pre-1). A fresh dispatch
        # begins a phase; an idempotent re-dispatch (crash-resume) must not
        # re-emit. Best-effort — never affects the loop's exit code.
        if result.get("action") == "dispatch" and not result.get("idempotent"):
            from .events import record_phase_started
            d = result.get("dispatch") or {}
            record_phase_started(project_root, phase=d.get("phase"),
                                 phase_task_id=d.get("phaseTaskId"),
                                 split_id=d.get("splitId"))
        print(json.dumps(result, indent=2))
        return 0 if result.get("action") in _OK_NEXT_ACTIONS else 1

    if args.command == "single-session-reload":
        # Rebuild pipeline context from run_config + compact summaries (never a
        # transcript) so the resuming master reads it verbatim. Lazy import keeps
        # single_session out of the base orchestrator surface.
        from single_session.orchestrator_context import reload_orchestrator_context

        context = reload_orchestrator_context(project_root)
        if context is None:
            print(json.dumps({"ok": False, "reason": "no_config"}))
            return 1
        print(json.dumps({"ok": True, "context": context}, indent=2))
        return 0

    # ----- SS5 resumability / recovery / human-gate -----------------------
    # Lazy import (recovery drags in the lifecycle mutators). Each function is
    # mode- and run-identity-gated, so a multi_session run is a no-op rejection.
    if args.command in ("single-session-resume", "single-session-gate",
                        "single-session-recover"):
        from .single_session_recovery import (
            mark_human_gate, recover_single_session, resume_run,
        )

        if args.command == "single-session-resume":
            result = resume_run(project_root, confirm=args.confirm)
            print(json.dumps(result, indent=2))
            return 0 if result.get("action") == "resume" else 1

        if args.command == "single-session-gate":
            result = mark_human_gate(
                project_root, phase_task_id=args.phase_task_id, phase=args.phase,
                paused=(args.state == "pause"), split_id=args.split_id,
            )
        else:  # single-session-recover
            result = recover_single_session(
                project_root, phase_task_id=args.phase_task_id,
                force_status=args.force_status,
            )
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    # single-session-apply
    result_path = Path(args.result_json)
    if not result_path.exists():
        print(
            json.dumps({"ok": False, "reason": "result_json_not_found", "path": str(result_path)}),
            file=sys.stderr,
        )
        return 1
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            json.dumps({"ok": False, "reason": "result_json_parse_error", "error": str(exc)}),
            file=sys.stderr,
        )
        return 1

    result = apply_phase_result(
        project_root,
        phase_task_id=args.phase_task_id,
        session_uuid=args.session_uuid,
        expected_version=args.version,
        result=payload,
    )
    # Durable phase-END at the apply boundary (B1/M-Pre-1) — pairs with the
    # phase_started emitted by single-session-next so the tracked
    # shipwright_events.jsonl holds complete start+end pairs (durations don't
    # depend on the gitignored/transient run_loop_events.jsonl). Only on a fresh
    # (non-idempotent) completion; best-effort, never affects the exit code.
    completion = result.get("completion") or {}
    pt = completion.get("phase_task") or {}
    if result.get("ok") and not completion.get("idempotent") and pt.get("status") in ("done", "failed"):
        from .events import record_phase_end
        record_phase_end(project_root, phase=pt.get("phase"), status=pt.get("status"),
                         phase_task_id=pt.get("phaseTaskId"), split_id=pt.get("splitId"))
    print(json.dumps(result, indent=2))
    if result.get("ok"):
        return 0
    reason = (result.get("completion") or {}).get("reason") or result.get("reason")
    return 2 if reason in _FAIL_CLOSED_REASONS else 1

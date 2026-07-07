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
    {"single-session-next", "single-session-apply"}
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
        print(json.dumps(result, indent=2))
        return 0 if result.get("action") in _OK_NEXT_ACTIONS else 1

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
    print(json.dumps(result, indent=2))
    if result.get("ok"):
        return 0
    reason = (result.get("completion") or {}).get("reason") or result.get("reason")
    return 2 if reason in _FAIL_CLOSED_REASONS else 1

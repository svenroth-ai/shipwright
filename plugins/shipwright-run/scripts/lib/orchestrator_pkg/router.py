"""F2 phase-lifecycle subcommand router for the orchestrator package.

Dispatches the lifecycle subcommands
(``get-phase-task``, ``find-phase-task-by-session-uuid``,
``validate-prerequisites``, ``claim-phase-task``, ``complete-phase-task``,
``mark-phase-failed``, ``recover-phase-task``, ``freeze-splits``,
``plan-next-phase``) to ``phase_task_lifecycle``. Owns the exit-code
mapping (0 = ok, 1 = generic error, 2 = fail-closed) shared with the
SessionStart / UserPromptSubmit hooks.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


FAIL_CLOSED_REASONS: frozenset[str] = frozenset({
    "wrong_skill", "duplicate_claim", "phase_already_terminal",
    "prereqs_unmet", "stale_version", "stale_session",
    "invalid_status", "invalid_status_for_completion",
})

LIFECYCLE_COMMANDS: frozenset[str] = frozenset({
    "get-phase-task",
    "find-phase-task-by-session-uuid",
    "validate-prerequisites",
    "claim-phase-task",
    "complete-phase-task",
    "mark-phase-failed",
    "recover-phase-task",
    "freeze-splits",
    "plan-next-phase",
})


def dispatch_lifecycle(args: argparse.Namespace, project_root: Path) -> int:
    """Run an F2 phase-lifecycle subcommand. Returns process exit code.

    Exit code map:
        0 -> result["ok"] is True
        2 -> fail-closed reasons (wrong_skill, duplicate_claim,
             phase_already_terminal, prereqs_unmet, stale_version,
             stale_session) — used by hooks for SessionStart/UserPromptSubmit blocks
        1 -> generic error (not_found, invalid args, etc.)
    """
    # Lazy import keeps the base orchestrator surface clean — the lifecycle
    # implementation drags in CAS / claim machinery (~660 LOC) which is
    # only needed for the F2 subcommands.
    from phase_task_lifecycle import (  # noqa: WPS433
        claim_phase_task,
        complete_phase_task,
        find_phase_task_by_session_uuid,
        freeze_splits,
        get_phase_task,
        mark_phase_failed,
        plan_next_phase,
        recover_phase_task,
        validate_prerequisites,
    )

    cmd = args.command
    result: dict[str, Any]
    if cmd == "get-phase-task":
        result = get_phase_task(project_root, args.phase_task_id)
    elif cmd == "find-phase-task-by-session-uuid":
        found = find_phase_task_by_session_uuid(project_root, args.session_uuid)
        result = {"ok": True, "phase_task": found} if found else {"ok": False, "reason": "not_found"}
    elif cmd == "validate-prerequisites":
        result = validate_prerequisites(project_root, args.phase_task_id)
    elif cmd == "claim-phase-task":
        result = claim_phase_task(
            project_root,
            phase_task_id=args.phase_task_id,
            session_uuid=args.session_uuid,
            expected_phase=args.expected_phase,
        )
    elif cmd == "complete-phase-task":
        result_path = Path(args.result_json)
        if not result_path.exists():
            print(json.dumps({"ok": False, "reason": "result_json_not_found",
                              "path": str(result_path)}), file=sys.stderr)
            return 1
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(json.dumps({"ok": False, "reason": "result_json_parse_error",
                              "error": str(exc)}), file=sys.stderr)
            return 1
        result = complete_phase_task(
            project_root,
            phase_task_id=args.phase_task_id,
            session_uuid=args.session_uuid,
            expected_version=args.version,
            result=payload,
        )
    elif cmd == "mark-phase-failed":
        result = mark_phase_failed(
            project_root,
            phase_task_id=args.phase_task_id,
            session_uuid=args.session_uuid,
            expected_version=args.version,
            error=args.error,
        )
    elif cmd == "recover-phase-task":
        result = recover_phase_task(
            project_root,
            phase_task_id=args.phase_task_id,
            force_status=args.force_status,
        )
    elif cmd == "freeze-splits":
        result = freeze_splits(project_root)
    elif cmd == "plan-next-phase":
        result = plan_next_phase(
            project_root, completed_phase_task_id=args.phase_task_id,
        )
    else:
        # Unreachable — argparse already validates choices
        print(json.dumps({"ok": False, "reason": "unknown_command", "command": cmd}),
              file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if result.get("ok"):
        return 0
    if result.get("reason") in FAIL_CLOSED_REASONS:
        return 2
    return 1

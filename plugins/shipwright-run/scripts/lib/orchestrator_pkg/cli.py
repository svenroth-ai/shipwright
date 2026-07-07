"""argparse + CLI dispatch for the orchestrator package.

Maps subcommand -> handler. Top-level subcommands (``write-config``,
``get-next-step``, ``update-step``, ``get-build-progress``) call the
high-level package functions directly. F2 phase-lifecycle subcommands
delegate to ``router.dispatch_lifecycle``.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .build_progress import get_build_progress
from .config_factory import create_config
from .constants import DEFAULT_RUN_MODE, PIPELINE_STEPS, RUN_MODES
from .router import LIFECYCLE_COMMANDS, dispatch_lifecycle
from .single_session_cli import SINGLE_SESSION_COMMANDS, dispatch_single_session
from .step_planning import get_next_step, update_step


def build_parser() -> argparse.ArgumentParser:
    """Construct the orchestrator CLI argparse tree.

    Extracted so tests / introspection can examine the parser without
    side effects.
    """
    parser = argparse.ArgumentParser(description="Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("write-config")
    p.add_argument("--scope", required=True, choices=["full_app", "extension"])
    p.add_argument("--profile", default=None)
    p.add_argument("--autonomy", default="guided", choices=["guided", "autonomous"])
    p.add_argument(
        "--mode", default=DEFAULT_RUN_MODE, choices=list(RUN_MODES),
        help=("Pipeline execution mode (SS1, additive). multi_session (default): "
              "each phase = its own external session. single_session: master "
              "drives phases via a phase-runner subagent in one conversation."),
    )
    p.add_argument("--deploy-target", default="jelastic-dev")
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser("get-next-step")
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser("update-step")
    p.add_argument("--project-root", default=".")
    # Iterate sec-report-and-orchestrator-decouple removed CONDITIONAL_STEPS
    # ("security"). Legacy phase_tasks with phase=security are still accepted
    # so users running update-step on an in-flight upgraded run aren't blocked.
    all_steps = PIPELINE_STEPS + ["security"]
    p.add_argument("--step", required=True, choices=all_steps)
    p.add_argument("--status", required=True, choices=["in_progress", "complete", "failed"])
    p.add_argument("--force", action="store_true", help="Skip validation (user override)")

    p = subparsers.add_parser("get-build-progress")
    p.add_argument("--project-root", default=".")

    # ----- F2 phase-task lifecycle subcommands ---------------------------
    # All return JSON on stdout. Exit codes:
    #   0 = ok
    #   1 = generic error (not_found, invalid args)
    #   2 = fail-closed (block) — used by phase_session_start.py /
    #       phase_user_prompt_validate.py

    p = subparsers.add_parser("get-phase-task")
    p.add_argument("--project-root", default=".")
    p.add_argument("--phase-task-id", required=True)

    p = subparsers.add_parser("find-phase-task-by-session-uuid")
    p.add_argument("--project-root", default=".")
    p.add_argument("--session-uuid", required=True)

    p = subparsers.add_parser("validate-prerequisites")
    p.add_argument("--project-root", default=".")
    p.add_argument("--phase-task-id", required=True)

    p = subparsers.add_parser("claim-phase-task")
    p.add_argument("--project-root", default=".")
    p.add_argument("--phase-task-id", required=True)
    p.add_argument("--session-uuid", required=True)
    p.add_argument("--expected-phase", required=True)

    p = subparsers.add_parser("complete-phase-task")
    p.add_argument("--project-root", default=".")
    p.add_argument("--phase-task-id", required=True)
    p.add_argument("--session-uuid", required=True)
    p.add_argument("--version", type=int, required=True,
                   help="Expected version (CAS check vs current task.version)")
    p.add_argument("--result-json", required=True,
                   help="Path to a JSON file containing the result payload")

    p = subparsers.add_parser("mark-phase-failed")
    p.add_argument("--project-root", default=".")
    p.add_argument("--phase-task-id", required=True)
    p.add_argument("--session-uuid", required=True)
    p.add_argument("--version", type=int, required=True)
    p.add_argument("--error", required=True)

    p = subparsers.add_parser("recover-phase-task")
    p.add_argument("--project-root", default=".")
    p.add_argument("--phase-task-id", required=True)
    p.add_argument("--force-status", default="awaiting_launch",
                   choices=["awaiting_launch", "failed", "skipped"])

    p = subparsers.add_parser("freeze-splits")
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser("plan-next-phase")
    p.add_argument("--project-root", default=".")
    p.add_argument("--phase-task-id", required=True,
                   help="phaseTaskId of the COMPLETED predecessor task")

    # ----- SS3 single-session orchestrator-loop subcommands --------------
    # The /shipwright-run master drives these two in ONE conversation under
    # `mode: single_session`. Both delegate to single_session_cli (which reuses
    # phase_task_lifecycle — no bespoke completion path). Exit codes match the
    # lifecycle map (0 ok, 2 fail-closed CAS reject, 1 guard/error).
    p = subparsers.add_parser("single-session-next")
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser("single-session-apply")
    p.add_argument("--project-root", default=".")
    p.add_argument("--phase-task-id", required=True)
    p.add_argument("--session-uuid", required=True)
    p.add_argument("--version", type=int, required=True,
                   help="Expected version (CAS check vs current task.version)")
    p.add_argument("--result-json", required=True,
                   help="Path to a JSON file containing the phase-runner result payload")

    # SS4: rebuild orchestrator context on resume — from run_config + compact
    # phase_tasks[].result summaries, never a transcript (context-budget bound).
    p = subparsers.add_parser("single-session-reload")
    p.add_argument("--project-root", default=".")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if args.command == "write-config":
        config = create_config(
            args.scope, args.profile, args.autonomy,
            args.deploy_target, project_root, mode=args.mode,
        )
        print(json.dumps(config, indent=2))

    elif args.command == "get-next-step":
        result = get_next_step(project_root)
        print(json.dumps(result, indent=2))

    elif args.command == "update-step":
        config = update_step(project_root, args.step, args.status, force=args.force)
        print(json.dumps(config, indent=2))

    elif args.command == "get-build-progress":
        result = get_build_progress(project_root)
        print(json.dumps(result, indent=2))

    elif args.command in LIFECYCLE_COMMANDS:
        return dispatch_lifecycle(args, project_root)

    elif args.command in SINGLE_SESSION_COMMANDS:
        return dispatch_single_session(args, project_root)

    return 0

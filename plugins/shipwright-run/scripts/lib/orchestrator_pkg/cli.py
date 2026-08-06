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
import sys
from pathlib import Path

from .build_progress import get_build_progress
from .config_factory import create_config
from .cli_update_step import dispatch_update_step
from .config_io import RunConfigUnreadable
from .constants import (
    DEFAULT_RUN_MODE,
    LEGACY_MODE_MESSAGE,
    LEGACY_MULTI_SESSION,
    PIPELINE_STEPS,
    RUN_MODES,
)
from .router import LIFECYCLE_COMMANDS, dispatch_lifecycle
from .single_session_cli import SINGLE_SESSION_COMMANDS, dispatch_single_session
from .step_planning import get_next_step


def _mode_value(value: str) -> str:
    """argparse ``type`` for ``--mode``: intercept the REMOVED mode with a real message.

    argparse applies ``type`` before ``choices``, so this fires first and raises the
    migration guidance. Without it, ``multi_session`` would fall through to the
    ``choices`` check and die with a bare ``invalid choice: 'multi_session'`` — which
    tells a user with a pre-removal config nothing about what to do.
    """
    if value == LEGACY_MULTI_SESSION:
        raise argparse.ArgumentTypeError(LEGACY_MODE_MESSAGE)
    return value


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
    # ``choices`` advertises ONLY the real mode, so `--help` and the usage line never
    # present the removed one as selectable. The ``type`` hook still intercepts the
    # removed literal FIRST (argparse applies type before choices), so passing it yields
    # the actionable migration message rather than a bare "invalid choice".
    p.add_argument(
        "--mode", default=DEFAULT_RUN_MODE, choices=list(RUN_MODES), type=_mode_value,
        help=("Pipeline execution mode. single_session is the SOLE mode: the master "
              "drives every phase via a phase-runner subagent in one conversation."),
    )
    p.add_argument("--deploy-target", default="jelastic-dev")
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser(
        "get-next-step",
        help='Report the next pipeline step. Exits 2 with {"blocked": true} when '
             "the run config exists but cannot be used (distinct from "
             "next_step: null, which means every step is complete).",
    )
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser("update-step")
    p.add_argument("--project-root", default=".")
    # Iterate sec-report-and-orchestrator-decouple removed CONDITIONAL_STEPS
    # ("security"). Legacy phase_tasks with phase=security are still accepted
    # so users running update-step on an in-flight upgraded run aren't blocked.
    all_steps = PIPELINE_STEPS + ["security"]
    p.add_argument("--step", required=True, choices=all_steps)
    p.add_argument("--status", required=True, choices=["in_progress", "complete", "failed"])
    p.add_argument(
        "--force", action="store_true",
        help=("Complete despite ask-level validation findings (user override). The "
              "validator still RUNS — force overrides the verdict, not the check — "
              "and what it found is recorded. Requires --force-reason."),
    )
    p.add_argument(
        "--force-reason", default=None,
        help=("Why the person decided to go ahead. Recorded verbatim in "
              "run_config.validation_overrides[] next to what the gate found, so "
              "'passed its checks' and 'was waved through' stay distinguishable "
              "(FR-01.01). Required with --force."),
    )

    p = subparsers.add_parser("get-build-progress")
    p.add_argument("--project-root", default=".")

    # ----- F2 phase-task lifecycle subcommands ---------------------------
    # All return JSON on stdout. Exit codes:
    #   0 = ok
    #   1 = generic error (not_found, invalid args)
    #   2 = fail-closed (CAS / prereq reject)

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

    # ----- Single-session orchestrator-loop subcommands -------------------
    # The /shipwright-run master drives these in ONE conversation.
    # They delegate to single_session_cli (which reuses
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

    # ----- SS5 resumability / recovery / human-gate observability ---------
    # Each is mode- and run-identity-gated: a config that is not an explicit
    # single_session run is a no-op rejection (nothing mutated, no file written).
    p = subparsers.add_parser("single-session-resume")
    p.add_argument("--project-root", default=".")
    p.add_argument("--confirm", action="store_true",
                   help="Commit the resume (emit the resume event). Omit for a "
                        "read-only confirm-card decision.")

    p = subparsers.add_parser("single-session-gate")
    p.add_argument("--project-root", default=".")
    p.add_argument("--phase-task-id", required=True)
    p.add_argument("--phase", required=True)
    p.add_argument("--split-id", default=None)
    p.add_argument("--state", required=True, choices=["pause", "resume"],
                   help="pause at an orchestrator-approve/hard-stop gate, or resume "
                        "after the human releases it.")

    p = subparsers.add_parser("single-session-recover")
    p.add_argument("--project-root", default=".")
    p.add_argument("--phase-task-id", required=True)
    p.add_argument("--force-status", default="awaiting_launch",
                   choices=["awaiting_launch", "failed", "skipped"])

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    try:
        return _dispatch(args, parser, project_root)
    except RunConfigUnreadable as exc:
        # The MUTATING arms propagate here; ``get-next-step`` catches inside
        # ``get_next_step`` and returns a blocked payload instead, so exactly one
        # of the two paths emits. Exit 2, not 1: "refused, nothing changed".
        print(json.dumps(exc.payload(), indent=2), file=sys.stderr)
        return 2


def _dispatch(args, parser, project_root: Path) -> int:
    if args.command == "write-config":
        # The removed mode is intercepted by the parser itself (``_mode_value``), so it
        # can never arrive here. ``create_config`` guards it a second time for library
        # callers that bypass the CLI.
        config = create_config(
            args.scope, args.profile, args.autonomy,
            args.deploy_target, project_root, mode=args.mode,
        )
        print(json.dumps(config, indent=2))

    elif args.command == "get-next-step":
        result = get_next_step(project_root)
        print(json.dumps(result, indent=2))
        # Blocked is still a RESULT, so it goes to stdout like every other arm
        # and is NOT echoed to stderr: one payload, one stream, with the exit
        # code carrying the failure. Echoing produced the same diagnostic twice
        # for anything aggregating both streams (external code review).
        #
        # Keyed on `blocked`, which the library contract designates as THE
        # discriminator, NOT on the `reason` string: `reason` is one of four
        # values, so renaming it would silently return 0 while printing a
        # blocked payload — a fail-open the exit-code tests could not catch.
        #
        # get_next_step CATCHES (a reporter must not crash), so this never
        # reaches main()'s handler; this branch is what makes the exit 2.
        if result.get("blocked"):
            return 2

    elif args.command == "update-step":
        return dispatch_update_step(args, parser, project_root)

    elif args.command == "get-build-progress":
        result = get_build_progress(project_root)
        print(json.dumps(result, indent=2))

    elif args.command in LIFECYCLE_COMMANDS:
        return dispatch_lifecycle(args, project_root)

    elif args.command in SINGLE_SESSION_COMMANDS:
        return dispatch_single_session(args, project_root)

    return 0

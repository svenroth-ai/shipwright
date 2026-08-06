"""The ``update-step`` CLI arm — the v1 completion path, and its two refusals.

Split out of ``cli.py`` the way ``router`` and ``single_session_cli`` already
are: that module dispatches command FAMILIES, and this one carries by far the
most policy of any single command. Keeping it inline pushed ``cli.py`` past its
300-LOC budget.

Both refusals below happen BEFORE ``update_step`` is called, so a rejected
invocation mutates nothing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config_io import is_single_session, read_run_config
from .step_planning import update_step


def dispatch_update_step(
    args: argparse.Namespace, parser: argparse.ArgumentParser, project_root: Path,
) -> int:
    """Run ``update-step``. Returns the process exit code.

    Propagates ``RunConfigUnreadable`` to ``cli.main``, which renders the
    actionable payload and exits 2.
    """
    # Drivability guard (iterate-2026-07-14-phase-invocation-mode). `update-step` is the
    # v1 completion path; in a driven single_session run `single-session-apply` owns
    # phase completion — run/SKILL.md is explicit: "Do NOT ... call `orchestrator
    # update-step`. The loop's two subcommands are the only way phases advance." Every
    # real caller of this command is a phase skill's completion step or the
    # generate_handoff_on_stop fallback; both reach it here at the CLI. Under the bug the
    # phase skills misclassified as standalone and skipped the call, so it stayed
    # harmless by accident. Correcting that classification would make them call it for
    # real — and update_step writes status="needs_validation" on any ask-level issue, the
    # same key resolve_next_dispatch reads BEFORE the phase_tasks frontier, permanently
    # halting a healthy run. So refuse it mechanically here rather than trusting prose.
    # The underlying update_step() function is unchanged: it still serves standalone /
    # legacy / adopted runs (no mode, or mode != single_session), and its state-machine
    # unit tests call it directly.
    #
    # STRICT: an unusable config used to read as `{}` here, which is falsy, so this
    # guard silently switched OFF and update_step went on to mutate a driven run —
    # the one thing the guard exists to prevent.
    cfg, _present = read_run_config(project_root, migrate=False)
    if cfg and is_single_session(cfg):
        print(json.dumps({
            "driven_run": True,
            "state_mutated": False,
            "step": args.step,
            "requested_status": args.status,
            "message": (
                "update-step is inert in a driven single_session run: single-session-apply "
                f"owns phase completion (run/SKILL.md). Ignored '{args.step}' -> "
                f"'{args.status}'."
            ),
        }, indent=2))
        return 0

    # An override with no recorded reason is the gap FR-01.01 exists to close,
    # so refuse it here with a readable message rather than letting update_step
    # raise ValueError. Placed AFTER the drivability guard so an inert command
    # stays inert, and gated on `complete` because `--force` on any other
    # status overrides nothing.
    #
    # This is DELIBERATELY stricter than the library on one arm: `update_step`
    # skips the demand for a standalone (bare-phase) run, because there the
    # gate never runs and nothing is recorded. The CLI still demands it —
    # a person typing `--force` at a terminal is making an interactive
    # override whether or not we have somewhere to file it. Do not "unify"
    # these by loosening the CLI.
    if (
        args.status == "complete"
        and args.force
        and not (args.force_reason or "").strip()
    ):
        parser.error(
            '--force requires --force-reason "<why>": the validator still runs '
            "under --force and what it found is recorded, but the person's "
            "reason for going ahead has to be recorded with it."
        )

    config = update_step(
        project_root, args.step, args.status,
        force=args.force, force_reason=args.force_reason,
    )
    print(json.dumps(config, indent=2))
    return 0

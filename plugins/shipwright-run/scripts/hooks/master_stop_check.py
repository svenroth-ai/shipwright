#!/usr/bin/env python3
"""Stop hook for the Master /shipwright-run session.

Observational only — never sets run.status. Final-status responsibility belongs to
complete-phase-task (Plan v4 §Master-Run-Lifecycle): that guarantees exactly-once
delivery without relying on the user reopening the master session.

Behaviour:
    1. If shipwright_run_config.json doesn't exist or isn't v2 -> exit 0.
    2. If the config is NOT a drivable single-session run (it records the removed
       ``multi_session`` mode, or no mode at all) -> print the migration notice.
       Keyed on the SAME explicit-literal predicate the loop and gate_policy use.
    3. If any phase_task is non-terminal: print a "still in progress" banner to
       stderr (Claude shows hook stderr to the user) telling the user how to
       resume — which, under single_session, is simply re-invoking /shipwright-run:
       the master DRIVES the pipeline, so there is nothing to launch elsewhere.
    4. If run.status == complete: print the celebration banner.
    5. If run.status == failed: print the diagnostic banner with the failed
       phase_task list so the user knows where to look.

Exit code: always 0. This hook never blocks the master session shutdown.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


CONFIG_NAME = "shipwright_run_config.json"

# Mirror of orchestrator_pkg.constants (a hook must not import the plugin lib).
#
# THE INVARIANT, shared with config_io.is_single_session and
# gate_policy.read_run_config_mode: a run is drivable IFF it records the explicit
# `single_session` literal. Keying this banner on `!= SINGLE_SESSION` (rather than
# `== multi_session`) keeps all three surfaces on the SAME predicate — a mode-less
# pre-SS1 config would otherwise get the normal "just re-invoke /shipwright-run"
# banner here, and then be refused by /shipwright-run itself.
SINGLE_SESSION = "single_session"
LEGACY_MULTI_SESSION = "multi_session"


def _summarise(config: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    tasks = config.get("phase_tasks") or []
    terminal = [t for t in tasks if t.get("status") in {"done", "skipped"}]
    failed = [t for t in tasks if t.get("status") == "failed"]
    pending = [t for t in tasks if t.get("status") in {"backlog", "awaiting_launch", "in_progress"}]
    return terminal, failed, pending


def _format_task_line(t: dict[str, Any]) -> str:
    split = f"/{t.get('splitId')}" if t.get("splitId") else ""
    ptk = str(t.get("phaseTaskId"))[-6:]
    return f"  - {t.get('phase')}{split} (ptk={ptk}) status={t.get('status')}"


def _orchestrator_path(project_root: Path) -> str:
    """Best-effort absolute path to orchestrator.py for paste-able commands.

    This hook lives in the shipwright-run plugin, so the orchestrator is two
    directory levels up. Falls back to a clearly-marked relative path so the
    output stays informative even if the lookup fails.
    """
    here = Path(__file__).resolve()
    candidate = here.parent.parent / "lib" / "orchestrator.py"
    if candidate.exists():
        return str(candidate)
    return "<plugin>/scripts/lib/orchestrator.py"


def _format_recover_command(task: dict[str, Any], orch_path: str,
                            *, force_status: str | None = None) -> str:
    extra = f" --force-status {force_status}" if force_status else ""
    # Always quote the orchestrator path — installations under directories with
    # spaces (Windows "Program Files", a OneDrive-synced folder) would otherwise
    # break when the user pastes the snippet into their shell.
    ptk = task.get("phaseTaskId")
    return f'      uv run "{orch_path}" recover-phase-task --phase-task-id {ptk}{extra}'


def _not_drivable_lines(run_id: str, mode: object) -> list[str]:
    """Banner for a run config that is NOT a drivable single-session run.

    Two causes, one fix — mirroring ``config_io.mode_rejection``: the config records the
    REMOVED ``multi_session`` mode, or it records no mode at all (a pre-SS1 run, which is
    not accused of a choice it never made).
    """
    if mode == LEGACY_MULTI_SESSION:
        cause = [
            "run.mode = multi_session — REMOVED.",
            "",
            "This run predates the single-session pipeline. Each phase used to run as its",
            "own external bound Claude session; that engine no longer exists.",
        ]
    else:
        cause = [
            f"run.mode = {mode!r} — not a drivable pipeline run.",
            "",
            "single_session is the sole mode, and a run must record it explicitly.",
        ]
    return [
        f"\n=== /shipwright-run Master Status ({run_id}) ===",
        *cause,
        "",
        "To migrate (no phase work is lost — phase_tasks[] are shared and re-claim is",
        "idempotent):",
        '  1. set "mode": "single_session" in shipwright_run_config.json',
        "  2. re-invoke /shipwright-run to resume",
        "",
        "See docs/migrations/multi-session-to-single-session.md.",
    ]


def run(project_root: Path) -> int:
    config_path = project_root / CONFIG_NAME
    if not config_path.exists():
        return 0
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    if config.get("schemaVersion") != 2:
        return 0

    run_id = config.get("runId", "unknown-run")

    mode = config.get("mode")
    if mode != SINGLE_SESSION:
        sys.stderr.write("\n".join(_not_drivable_lines(run_id, mode)) + "\n")
        return 0

    status = config.get("status", "unknown")
    terminal, failed, pending = _summarise(config)
    orch_path = _orchestrator_path(project_root)

    lines: list[str] = []
    lines.append(f"\n=== /shipwright-run Master Status ({run_id}) ===")
    lines.append(f"run.status = {status}")
    lines.append(
        f"  terminal: {len(terminal)}, failed: {len(failed)}, pending: {len(pending)}"
    )
    lines.append("")

    if status == "complete":
        lines.append("PIPELINE COMPLETE.")
        for t in terminal:
            lines.append(_format_task_line(t))
        lines.append("")
        lines.append("All phase tasks are terminal. /shipwright-run is done.")
    elif status == "failed":
        lines.append("PIPELINE FAILED.")
        for t in failed:
            lines.append(_format_task_line(t))
            for err in t.get("errors", []):
                lines.append(f"      error: {err}")
            lines.append("    To recover (paste in your terminal):")
            lines.append(_format_recover_command(
                t, orch_path, force_status="awaiting_launch",
            ))
            lines.append(
                "    (use --force-status skipped to move on without re-running this phase)"
            )
        lines.append("")
        lines.append("After recover-phase-task, re-invoke /shipwright-run — the master")
        lines.append("resumes the loop from the recovered phase.")
    elif pending:
        lines.append("PIPELINE IN PROGRESS — the master session ended mid-run.")
        lines.append("")
        for t in pending:
            lines.append(_format_task_line(t))
        lines.append("")
        lines.append("The master DRIVES the pipeline in one conversation, so there is")
        lines.append("nothing to launch separately: re-invoke /shipwright-run. It prints")
        lines.append("a resume card, then continues from the frontier phase.")
        # Only offer the recover escape hatch when there IS something wedged — otherwise
        # the banner ends on a colon with no command under it.
        wedged = [t for t in pending if t.get("status") == "in_progress"]
        if wedged:
            lines.append("")
            lines.append("A task left in_progress (the master died mid-phase) is re-dispatched")
            lines.append("idempotently on resume. Only for a genuinely wedged task:")
            for t in wedged:
                lines.append(_format_recover_command(t, orch_path))
    else:
        lines.append("(no actionable status — config in unexpected state)")

    sys.stderr.write("\n".join(lines) + "\n")
    return 0


def main() -> int:
    project_root_env = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")
    project_root = Path(project_root_env).resolve() if project_root_env else Path.cwd()
    return run(project_root)


if __name__ == "__main__":
    sys.exit(main())

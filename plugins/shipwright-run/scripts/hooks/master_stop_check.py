#!/usr/bin/env python3
"""Stop hook for the Master /shipwright-run session (F3a).

Observational only — never sets run.status. Final-status responsibility
moved to complete-phase-task (Plan v4 §Master-Run-Lifecycle): this guarantees
exactly-once delivery without relying on the user reopening the master
session.

Behaviour:
    1. If shipwright_run_config.json doesn't exist or isn't v2 -> exit 0.
    2. If any phase_task is non-terminal: print a "still in progress" banner
       to stderr (Claude shows hook stderr to the user) so they know the
       master is intentionally idling.
    3. If run.status == complete: print the celebration banner.
    4. If run.status == failed: print the diagnostic banner with the
       failed phase_task list so the user knows where to look.

Exit code: always 0. This hook never blocks the master session shutdown.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


CONFIG_NAME = "shipwright_run_config.json"


def _summarise(config: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    tasks = config.get("phase_tasks") or []
    terminal = [t for t in tasks if t.get("status") in {"done", "skipped"}]
    failed = [t for t in tasks if t.get("status") == "failed"]
    pending = [t for t in tasks if t.get("status") in {"backlog", "awaiting_launch", "in_progress"}]
    return terminal, failed, pending


def _format_task_line(t: dict[str, Any]) -> str:
    split = f"/{t.get('splitId')}" if t.get("splitId") else ""
    return f"  - {t.get('phase')}{split} (ptk={t.get('phaseTaskId')[-6:]}) status={t.get('status')}"


def _short_run_id(run_id: str) -> str:
    """Drop the 'run-' prefix and take the first 4 hex chars (matches the
    master skill's banner naming convention)."""
    if run_id.startswith("run-"):
        return run_id[4:8]
    return run_id[:4]


def _name_suffix(task: dict[str, Any]) -> str:
    split_id = task.get("splitId")
    if split_id:
        return f"{task.get('phase')} / {split_id}"
    return str(task.get("phase"))


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


def _format_launch_command(task: dict[str, Any], project_root: Path,
                           run_id: str) -> str:
    """Render the paste-able `claude --session-id ...` launch command for an
    awaiting_launch task. Mirrors the master skill's Step 5 banner format so
    the user sees the same command shape across surfaces."""
    return (
        f"      claude --session-id {task.get('sessionUuid')} "
        f"--add-dir \"{project_root}\" "
        f"--name 'Run-{_short_run_id(run_id)} / {_name_suffix(task)}' "
        f"'{task.get('slashCommand')}'"
    )


def _format_recover_command(task: dict[str, Any], orch_path: str,
                            *, force_status: str | None = None) -> str:
    extra = f" --force-status {force_status}" if force_status else ""
    # Always quote the orchestrator path — installations under directories
    # with spaces (e.g. Windows "AI Backup - Documents") would otherwise
    # break when the user pastes the snippet into their shell.
    return (
        f"      uv run \"{orch_path}\" recover-phase-task "
        f"--phase-task-id {task.get('phaseTaskId')}{extra}"
    )


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
        lines.append(
            "After recover-phase-task, re-invoke /shipwright-run to print a "
            "fresh launch card,"
        )
        lines.append("or paste the WebUI Kanban launch command if the WebUI is in use.")
    elif pending:
        lines.append("PIPELINE IN PROGRESS — master is intentionally idling.")
        lines.append("")
        lines.append("Pending phase tasks. To continue, paste the matching")
        lines.append("launch command into a new terminal:")
        lines.append("")
        for t in pending:
            lines.append(_format_task_line(t))
            if t.get("status") == "awaiting_launch":
                lines.append(_format_launch_command(t, project_root, run_id))
            elif t.get("status") == "in_progress":
                lines.append(
                    "      (already claimed by a phase session — close it cleanly,"
                )
                lines.append(
                    "       or run recover-phase-task if it crashed:"
                )
                lines.append(_format_recover_command(t, orch_path))
                lines.append(
                    "       and then re-launch with the command above)"
                )
            lines.append("")
        lines.append(
            "(Or open the master with /shipwright-run again — the resume banner "
            "prints the next launch card.)"
        )
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

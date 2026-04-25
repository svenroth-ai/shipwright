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

    lines: list[str] = []
    lines.append(f"\n=== /shipwright-run Master Status ({run_id}) ===")
    lines.append(f"run.status = {status}")
    lines.append(f"  terminal: {len(terminal)}, failed: {len(failed)}, pending: {len(pending)}")
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
        lines.append("")
        lines.append(
            "Use orchestrator.py recover-phase-task --phase-task-id <ptk> "
            "to release a stuck task."
        )
    elif pending:
        lines.append("PIPELINE IN PROGRESS — master is intentionally idling.")
        lines.append("")
        lines.append("Pending phase tasks (waiting for external launch):")
        for t in pending:
            lines.append(_format_task_line(t))
        lines.append("")
        lines.append(
            "Open a new terminal and paste the launch command from the "
            "WebUI Kanban (or check shipwright_run_config.json.phase_tasks)."
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

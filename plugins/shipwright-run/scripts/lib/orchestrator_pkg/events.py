"""Event-recording helpers for the orchestrator package.

These functions write ``pipeline_migration`` and
``compliance_update_failed`` events via the shared ``record_event.py``
tool. Non-blocking on failure — orchestrator behaviour must not depend
on event-log durability.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .constants import _SHARED_SCRIPTS


def _record_pipeline_migration_event(
    project_root: Path,
    *,
    removed: list[str],
    skipped_security_phase_task_ids: list[str] | None = None,
) -> None:
    """Record a ``pipeline_migration`` event. Non-blocking on failure."""
    record_script = _SHARED_SCRIPTS / "tools" / "record_event.py"
    if not record_script.exists():
        return
    parts: list[str] = []
    if removed:
        parts.append(f"removed from pipeline: {', '.join(removed)}")
    if skipped_security_phase_task_ids:
        parts.append(
            "auto-skipped security phase_tasks: "
            + ", ".join(skipped_security_phase_task_ids)
        )
    detail = "; ".join(parts) if parts else "no-op"
    try:
        subprocess.run(
            [sys.executable, str(record_script),
             "--project-root", str(project_root),
             "--type", "pipeline_migration",
             "--detail", detail],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
            cwd=str(project_root),
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def _record_compliance_update_failed(
    project_root: Path, phase: str, *, reason: str,
) -> None:
    """Record a ``compliance_update_failed`` event. Non-blocking on failure."""
    record_script = _SHARED_SCRIPTS / "tools" / "record_event.py"
    if not record_script.exists():
        return
    try:
        subprocess.run(
            [sys.executable, str(record_script),
             "--project-root", str(project_root),
             "--type", "compliance_update_failed",
             "--phase", phase,
             "--detail", reason],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
            cwd=str(project_root),
        )
    except (subprocess.TimeoutExpired, OSError):
        pass

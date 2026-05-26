"""Legacy-pipeline migration helpers for the orchestrator package.

Drops removed phases (``compliance``, ``security``) from configs that
existed before those phases were retired, and migrates in-flight
security phase_tasks to ``skipped`` so the pipeline can drain.

Tests patch ``orchestrator._record_pipeline_migration_event`` to assert
on call-count / args. To preserve that contract after the B5 split,
the event-recording call here goes through the shim module
(``orchestrator``) via a late import, so the patched binding wins.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import _LEGACY_PIPELINE_ENTRIES


def _migrate_legacy_pipeline_if_needed(
    project_root: Path, config: dict[str, Any],
) -> dict[str, Any]:
    """Drop legacy entries from ``config["pipeline"]`` and migrate in-flight
    security phase_tasks (when present).

    Legacy entries (see ``_LEGACY_PIPELINE_ENTRIES``):
    - ``compliance`` — auto-background side-effect since plan v7 Option Z
    - ``security`` — manual / CI since iterate sec-report-and-orchestrator-decouple

    ``completed_steps`` is left untouched so the historical record of
    completed runs is preserved.

    For ``security`` specifically, also iterate ``phase_tasks[]`` and skip any
    non-terminal entry (``backlog`` / ``awaiting_launch``) — they would
    otherwise sit forever waiting for a phase that the orchestrator no longer
    plans. ``in_progress`` security phase_tasks are LEFT ALONE (CAS-safe; the
    user has an active session and must recover manually per the migration
    notice).

    Idempotent: once filtered, subsequent loads short-circuit. Mutates
    ``config`` and persists via ``save_run_config`` only when changes occur.
    """
    pipeline = config.get("pipeline")
    pipeline_stale: list[str] = []
    if isinstance(pipeline, list):
        pipeline_stale = [s for s in pipeline if s in _LEGACY_PIPELINE_ENTRIES]

    skipped_security_ids: list[str] = []
    if any(s == "security" for s in pipeline_stale) or _has_non_terminal_security_phase_tasks(config):
        now_iso = datetime.now(timezone.utc).isoformat()
        skipped_security_ids = _migrate_in_flight_security_tasks(config, now_iso)

    if not pipeline_stale and not skipped_security_ids:
        return config

    config = dict(config)
    if pipeline_stale and isinstance(pipeline, list):
        config["pipeline"] = [s for s in pipeline if s not in _LEGACY_PIPELINE_ENTRIES]
    # Lazy imports — config_io importing us is the circular edge we
    # avoid; orchestrator (shim) is imported late so tests can patch
    # _record_pipeline_migration_event via the shim namespace.
    from .config_io import save_run_config
    save_run_config(project_root, config)

    orchestrator_mod = sys.modules.get("orchestrator")
    if orchestrator_mod is not None:
        orchestrator_mod._record_pipeline_migration_event(
            project_root,
            removed=pipeline_stale,
            skipped_security_phase_task_ids=skipped_security_ids,
        )
    else:
        # Defensive fallback when the shim hasn't been imported yet
        # (e.g. someone imports the package directly without going
        # through orchestrator.py). Use the package binding.
        from .events import _record_pipeline_migration_event
        _record_pipeline_migration_event(
            project_root,
            removed=pipeline_stale,
            skipped_security_phase_task_ids=skipped_security_ids,
        )

    _print_security_decouple_notice(
        pipeline_stale=pipeline_stale,
        skipped_security_ids=skipped_security_ids,
        config=config,
    )
    return config


def _has_non_terminal_security_phase_tasks(config: dict[str, Any]) -> bool:
    """Return True if ``config["phase_tasks"]`` contains any security entry
    in backlog / awaiting_launch / in_progress status."""
    for task in config.get("phase_tasks", []) or []:
        if not isinstance(task, dict):
            continue
        if task.get("phase") == "security" and task.get("status") in {
            "backlog", "awaiting_launch", "in_progress",
        }:
            return True
    return False


def _migrate_in_flight_security_tasks(
    config: dict[str, Any], now_iso: str,
) -> list[str]:
    """Skip non-terminal security phase_tasks (backlog / awaiting_launch).

    Conservative: leaves ``in_progress`` tasks alone — the user has an active
    session whose CAS-version we'd collide with. The migration notice
    instructs the user to recover those manually.

    Returns the list of phase_task IDs that were skipped.
    """
    skipped_ids: list[str] = []
    for task in config.get("phase_tasks", []) or []:
        if not isinstance(task, dict):
            continue
        if task.get("phase") != "security":
            continue
        if task.get("status") not in {"backlog", "awaiting_launch"}:
            continue
        task["status"] = "skipped"
        task["completedAt"] = now_iso
        task["result"] = {
            "ok": False,
            "skipped_by": "security-decouple-migration",
        }
        skipped_ids.append(task.get("phaseTaskId", ""))

    if skipped_ids:
        completed = config.setdefault("completed_phase_task_ids", [])
        if isinstance(completed, list):
            for tid in skipped_ids:
                if tid and tid not in completed:
                    completed.append(tid)
    return skipped_ids


def _print_security_decouple_notice(
    *,
    pipeline_stale: list[str],
    skipped_security_ids: list[str],
    config: dict[str, Any],
) -> None:
    """Print a user-facing notice when security is removed from the pipeline.

    Surfaces both the legacy-pipeline-array migration AND the in-flight
    phase_task migration, plus the manual-recover hint for any in_progress
    security task that was left untouched.
    """
    if "security" not in pipeline_stale and not skipped_security_ids:
        return

    in_progress_ids = [
        t.get("phaseTaskId")
        for t in (config.get("phase_tasks") or [])
        if isinstance(t, dict)
        and t.get("phase") == "security"
        and t.get("status") == "in_progress"
    ]

    lines = [
        "[shipwright-run] Notice: 'security' is no longer a pipeline phase.",
    ]
    if "security" in pipeline_stale:
        lines.append("  - 'security' removed from config.pipeline (legacy migration).")
    if skipped_security_ids:
        lines.append(
            f"  - {len(skipped_security_ids)} non-terminal security phase_task(s) auto-skipped: "
            + ", ".join(skipped_security_ids)
        )
    if in_progress_ids:
        lines.append("  - Found in-progress security phase_task(s); not auto-migrated:")
        for tid in in_progress_ids:
            lines.append(
                f"      uv run plugins/shipwright-run/scripts/lib/orchestrator.py "
                f"recover-phase-task --phase-task-id {tid} --force-status skipped"
            )
    lines.append(
        "  Run /shipwright-security manually for ad-hoc scans, or activate "
        ".github/workflows/security.yml triggers for scheduled scans."
    )
    print("\n".join(lines), file=sys.stderr)

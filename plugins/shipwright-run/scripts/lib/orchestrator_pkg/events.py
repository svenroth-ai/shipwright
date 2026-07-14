"""Event-recording helpers for the orchestrator package.

These functions write ``pipeline_migration`` and
``compliance_update_failed`` events via the shared ``record_event.py``
tool. Non-blocking on failure — orchestrator behaviour must not depend
on event-log durability.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

import json
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


def _run_id_of(project_root: Path) -> str:
    """Best-effort ``runId`` from the run config (``unknown-run`` on any error).

    Tolerates a config that is valid JSON but not an object (``null`` / list /
    string from a corrupt or hand-edited file) — ``.get`` on a non-dict would
    otherwise raise and crash a phase-entry path this must never break.
    """
    try:
        cfg = json.loads(
            (project_root / "shipwright_run_config.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return "unknown-run"
    if not isinstance(cfg, dict):
        return "unknown-run"
    return cfg.get("runId", "unknown-run")


def _emit_phase_event(
    project_root: Path, event_type: str, phase: str | None,
    *, phase_task_id: str | None, split_id: str | None,
) -> None:
    """Best-effort emit of a durable phase event via ``record_event.py``.

    Shared by the phase-START and phase-END emitters below. Never raises — a
    telemetry write must never crash a phase entry/exit path. ``errors=replace``
    guards the Windows cp1252 child-output decode landmine (an undecodable byte
    would otherwise raise ``UnicodeDecodeError``, which the except below does
    NOT catch).
    """
    record_script = _SHARED_SCRIPTS / "tools" / "record_event.py"
    if not record_script.exists() or not phase:
        return
    detail = {
        "phaseTaskId": phase_task_id,
        "splitId": split_id,
        "runId": _run_id_of(project_root),
    }
    cmd = [
        sys.executable, str(record_script),
        "--project-root", str(project_root),
        "--type", event_type,
        "--phase", phase,
        "--detail", json.dumps(detail),
    ]
    # Promote splitId to a top-level record_event field so phase_completed dedups
    # by (phase, splitId) — a multi-split phase records one end per split rather
    # than collapsing to the first (iterate-2026-07-11-phase-completed-per-split).
    # `is not None`: forward any explicit splitId (exact (phase, splitId) identity).
    if split_id is not None:
        cmd += ["--split-id", str(split_id)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10, cwd=str(project_root),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        # Never crash the loop — but surface the miss (mirrors observability).
        sys.stderr.write(f"[events] {event_type} emit failed: {exc}\n")
        return
    if proc.returncode != 0:
        sys.stderr.write(
            f"[events] {event_type} emit exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout or '').strip()[:200]}\n"
        )


def record_phase_started(
    project_root: Path, *, phase: str | None,
    phase_task_id: str | None = None, split_id: str | None = None,
) -> None:
    """Durable phase-ENTRY event (the counterpart of ``phase_completed``).

    In ``single_session`` (the default + sole mode) phases run as phase-runner
    subagents that do NOT fire the phase Stop/SessionStart hooks, so this is
    emitted at the ``single-session-next`` boundary where the master claims +
    begins a phase. B1/M-Pre-1 (concept §5a): per-phase START timestamps for
    the WebUI PhaseRail. Additive — no existing event changes.
    """
    _emit_phase_event(project_root, "phase_started", phase,
                      phase_task_id=phase_task_id, split_id=split_id)


def record_phase_end(
    project_root: Path, *, phase: str | None, status: str,
    phase_task_id: str | None = None, split_id: str | None = None,
) -> None:
    """Durable phase-END event for a ``single_session`` phase.

    ``phase_completed`` for a
    done phase, ``phase_failed`` for a failed one. Without it the single_session
    END lands ONLY in the TRANSIENT ``run_loop_events.jsonl``
    (``obs.emit_phase_result``), so per-phase durations were not computable from
    the tracked ``shipwright_events.jsonl`` alone. Emitted at the
    ``single-session-apply`` boundary.

    Pairing is per ``(runId, phase, splitId)``: record_event dedups
    ``phase_completed`` by the ``(phase, splitId)`` PAIR, so a multi-split
    pipeline phase (build/plan fan out one phase_task per split, all sharing the
    same ``phase``) records ONE end per split (``split_id`` is promoted to a
    top-level ``--split-id``/``splitId`` field). The per-phase span derives as
    min(``phase_started``) .. max(``phase_completed``) across the phase's splits;
    per-split duration bars derive from each split's own start/end. A single-split
    phase carries ``splitId=None`` and pairs exactly, as before.
    (iterate-2026-07-11-phase-completed-per-split, following M-Pre-1.)
    """
    event_type = "phase_failed" if status == "failed" else "phase_completed"
    _emit_phase_event(project_root, event_type, phase,
                      phase_task_id=phase_task_id, split_id=split_id)


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

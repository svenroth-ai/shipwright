"""Run-config factory for the orchestrator package.

Builds the initial v2 multi-session config (``shipwright_run_config.json``)
including the seed phase_task for the project phase. Also exposes
``build_pipeline`` — the static pipeline-step list — as a function so
callers that want the live planning order go through one entry point.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from phase_state_machine import freeze_run_conditions, initial_phase_spec

from .config_io import load_run_config, save_run_config
from .constants import DEFAULT_RUN_MODE, PIPELINE_STEPS, RUN_MODES, SCHEMA_VERSION


def build_pipeline() -> list[str]:
    """Return the static orchestrator phase list.

    Iterate ``sec-report-and-orchestrator-decouple`` removed the conditional-
    steps mechanism: security is no longer auto-inserted after test. Run
    ``/shipwright-security`` manually or activate
    ``.github/workflows/security.yml``.
    """
    return PIPELINE_STEPS.copy()


def _new_run_id() -> str:
    """Stable run id: 'run-' + first 8 hex chars of a uuid4."""
    return "run-" + uuid.uuid4().hex[:8]


def _new_phase_task_id() -> str:
    return "ptk-" + uuid.uuid4().hex[:8]


def _build_initial_phase_task(now_iso: str) -> dict[str, Any]:
    """Construct the initial phase_tasks[] entry for the project phase.

    Pre-binds a sessionUuid so the WebUI/launch-card can render the user's
    paste-able command immediately. The Plan v3 launchCommandHint is
    populated by the launch-card renderer (WebUI or master skill banner) —
    we store the slashCommand here as the authoritative source.
    """
    spec = initial_phase_spec()
    return {
        "phaseTaskId": _new_phase_task_id(),
        "phase": spec["phase"],
        "splitId": spec["splitId"],
        "sessionUuid": str(uuid.uuid4()),
        "version": 1,
        "status": "awaiting_launch",
        "title": "project",
        "description": "Decompose requirements into splits + specs",
        "slashCommand": spec["slashCommand"],
        "prerequisites": spec["prerequisites"],
        "claimedBySessionUuid": None,
        "claimAttemptedAt": None,
        "executionCount": 0,
        "createdAt": now_iso,
        "awaitingLaunchAt": now_iso,
        "startedAt": None,
        "completedAt": None,
        "result": None,
        "errors": [],
    }


def create_config(
    scope: str,
    profile: Optional[str],
    autonomy: str,
    deploy_target: str,
    project_root: Path,
    mode: str = DEFAULT_RUN_MODE,
) -> dict[str, Any]:
    """Create initial orchestrator config (v2 schema).

    If a standalone config exists (from prior /shipwright-project or similar),
    merges its completed_steps so already-finished phases are not repeated.
    Backwards-compat note: standalone configs use the legacy v1 fields
    (current_step / completed_steps); we still merge those, but the new
    config we write is always v2 (schemaVersion: 2 + phase_tasks[]).

    ``mode`` (Campaign 2026-07-07, SS1) selects the pipeline execution mode
    (``multi_session`` default | ``single_session``). It is validated against
    ``RUN_MODES`` and always written to the config so downstream readers never
    have to guess. The initial phase_tasks[] seed is mode-independent — the
    single-session orchestrator loop (SS3) consumes the SAME phase_tasks[] via
    the phase_task_lifecycle helpers, so no parallel seed shape is created here.
    """
    if mode not in RUN_MODES:
        raise ValueError(
            f"invalid mode {mode!r}; expected one of {', '.join(RUN_MODES)}"
        )
    pipeline = build_pipeline()
    now_iso = datetime.now(timezone.utc).isoformat()
    run_id = _new_run_id()

    # Merge: carry over completed_steps from standalone invocations (legacy v1 shape)
    existing = load_run_config(project_root)
    prior_completed: list[str] = []
    if existing.get("standalone") and existing.get("completed_steps"):
        prior_completed = [s for s in existing["completed_steps"] if s in pipeline]

    # Freeze runConditions at creation. Iterate
    # `sec-report-and-orchestrator-decouple` (2026): `securityEnabled` is
    # always False because security is no longer an orchestrator phase. We
    # still pass `aikido_client_id` so the diagnostic
    # `aikidoClientIdPresent` flag stays accurate for WebUI / CLI display.
    aikido_id = os.environ.get("AIKIDO_CLIENT_ID")
    run_conditions = freeze_run_conditions(aikido_client_id=aikido_id)

    # Initial phase_tasks[] — only the project task is materialized at run start.
    # Subsequent tasks are appended by complete-phase-task → plan_next_phase
    # in F2. If standalone-merge already completed 'project', we still emit the
    # initial entry but with status=skipped to keep the audit trail clean.
    initial_task = _build_initial_phase_task(now_iso)
    if "project" in prior_completed:
        initial_task["status"] = "skipped"
        initial_task["completedAt"] = now_iso

    # Determine v1-compat starting step (first uncompleted pipeline step).
    # Kept parallel to phase_tasks[] until F2 wires the phase-lifecycle
    # subcommands (claim/complete/recover) — until then, update_step() and
    # get_next_step() still rely on current_step/completed_steps.
    remaining = [s for s in pipeline if s not in prior_completed]
    current_step = remaining[0] if remaining else None

    config: dict[str, Any] = {
        # --- v2 fields ---
        "schemaVersion": SCHEMA_VERSION,
        "runId": run_id,
        # Additive dual-mode selector (SS1). Default multi_session preserves the
        # external UUID-bound phase-session model; single_session is honored by
        # the SS3 in-conversation orchestrator loop.
        "mode": mode,
        "runConditions": run_conditions,
        "splits_frozen": [],
        "completed_phase_task_ids": (
            [initial_task["phaseTaskId"]] if initial_task["status"] == "skipped" else []
        ),
        "phase_tasks": [initial_task],
        # --- v1 compat (kept until F2 hard-cut) ---
        "scope": scope,
        "profile": profile,
        "autonomy": autonomy,
        "deploy_target": deploy_target,
        "pipeline": pipeline,
        "status": "in_progress" if current_step else "complete",
        "current_step": current_step,
        "completed_steps": prior_completed,
        "created_at": now_iso,
        # Iterate 12.0 (ADR-027): per-phase audit trail parallel to
        # iterate_history. Populated by tools/append_phase_history.py from
        # 12.1+ phase canon wiring. Empty on fresh creation.
        "phase_history": {},
    }

    # Carry over phase_history from an existing standalone config so a
    # subsequent /shipwright-run doesn't lose audit-trail entries.
    if existing.get("phase_history"):
        config["phase_history"] = existing["phase_history"]

    save_run_config(project_root, config)
    return config

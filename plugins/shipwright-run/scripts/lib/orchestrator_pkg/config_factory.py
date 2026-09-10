"""Run-config factory for the orchestrator package.

Builds the initial v2 pipeline config (``shipwright_run_config.json``)
including the seed phase_task for the project phase. Also exposes
``build_pipeline`` — the static pipeline-step list — as a function so
callers that want the live planning order go through one entry point.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from phase_state_machine import freeze_run_conditions, initial_phase_spec

from .config_io import RunConfigUnreadable, read_run_config, save_run_config
from .constants import (
    CONFIG_NAME,
    DEFAULT_RUN_MODE,
    LEGACY_MODE_MESSAGE,
    LEGACY_MULTI_SESSION,
    PIPELINE_STEPS,
    RUN_MODES,
    SCHEMA_VERSION,
)

# `.constants` (imported above) already put `shared/scripts` on sys.path.
from lib.handoff_phase_status import (  # noqa: E402
    phase_tasks_has_usable_entries,
    phase_tasks_progress,
)


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

    ``sessionUuid`` is a pre-bound uuid4 used as the phase task's CAS CLAIM
    TOKEN by the single-session loop (``single_session_loop.next_dispatch``).
    It is NOT a Claude session id: under the removed multi_session mode it
    doubled as the bound session id a phase was launched with, but the phase
    runner is now a subagent of the master and has no bound session of its own. ``slashCommand`` remains the authoritative phase entry point.
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


def build_v1_phase_task(phase: str, status: str, *, now: str) -> dict[str, Any]:
    """Build one ``phase_tasks[]`` entry for a phase advanced OUTSIDE the CAS
    phase-task lifecycle — the v1 ``update_step`` path (standalone / legacy /
    adopted runs) and this module's own standalone-config merge, below.

    Mirrors ``plugins/shipwright-adopt/scripts/lib/adopted_phase_tasks.py``'s
    ``build_adopted_phase_task`` shape (not imported: that would be the
    ADR-045 cross-plugin ``lib``-namespace collision that module's own
    docstring documents for the reverse direction) but carries no
    ``establishedAtAdoption`` marker — that flag means "never executed,
    backfilled at adoption time"; a v1 phase genuinely ran (or is running,
    or failed), via a mechanism the schema's ``PhaseTask`` shape does not
    otherwise distinguish. Campaign p4-04-retire-write-once-steps,
    sub-iterate s5: replaces the write-once ``current_step``/
    ``completed_steps`` fields this campaign retires.
    """
    terminal = status in {"done", "failed", "skipped"}
    active = status not in {"backlog", "awaiting_launch"}
    return {
        "phaseTaskId": _new_phase_task_id(),
        "phase": phase,
        "splitId": None,
        "sessionUuid": str(uuid.uuid4()),
        "version": 1,
        "status": status,
        "title": phase,
        "description": (
            "Advanced via the v1 update_step path (standalone / legacy / "
            "adopted run, no orchestrator session)."
        ),
        "slashCommand": f"/shipwright-{phase}",
        "prerequisites": [],
        "claimedBySessionUuid": None,
        "claimAttemptedAt": None,
        "executionCount": 1 if active else 0,
        "createdAt": now,
        "awaitingLaunchAt": None,
        "startedAt": now if active else None,
        "completedAt": now if terminal else None,
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
    merges its ``phase_tasks[]``-derived progress so already-finished phases
    are not repeated. The new config we write is always v2 (schemaVersion: 2
    + phase_tasks[]) — there is no other shape left to merge from: the v1
    ``current_step``/``completed_steps`` fields, and every writer of them,
    are retired (campaign p4-04-retire-write-once-steps, sub-iterate s5).

    ``mode`` is always written to the config so downstream readers (and the
    WebUI, which renders this contract) never have to guess. ``single_session``
    is the sole mode; the removed ``multi_session`` literal is rejected here
    with the migration message rather than an opaque enum error, so the factory
    can never seed a run under an execution model that no longer exists.
    """
    if mode == LEGACY_MULTI_SESSION:
        raise ValueError(LEGACY_MODE_MESSAGE)
    if mode not in RUN_MODES:
        raise ValueError(
            f"invalid mode {mode!r}; expected one of {', '.join(RUN_MODES)}"
        )
    pipeline = build_pipeline()
    now_iso = datetime.now(timezone.utc).isoformat()
    run_id = _new_run_id()

    # Merge: carry over phase_tasks[]-derived progress from standalone invocations.
    #
    # BEST-EFFORT, by category. This is the documented recovery path — an unusable
    # config is what the operator is told to fix by deleting and re-running — so
    # damaged CONTENT must not stop it: we are here to replace that file, and the
    # only thing lost is a merge of steps we cannot read anyway. The tolerant
    # reader would have crashed on the `decode` arm, which it propagates, making
    # the advertised recovery impossible for a non-UTF-8 file.
    #
    # An `io` failure still propagates: it will defeat the write below regardless,
    # and "delete it and re-run" is the wrong thing to tell someone whose file is
    # merely unreadable by permissions.
    try:
        existing, _present = read_run_config(project_root)
    except RunConfigUnreadable as exc:
        if exc.category == "io":
            raise
        print(json.dumps({
            "warning": "Replacing an unusable orchestrator config",
            "error_category": "validation",
            "what_failed": f"Read the prior {CONFIG_NAME} to merge its progress",
            "exception": exc.detail,
            "alternative": "Prior progress was NOT merged; the new config starts clean",
        }), file=sys.stderr)
        existing = {}

    prior_completed: list[str] = []
    if existing.get("standalone"):
        _, existing_completed = phase_tasks_progress(existing)
        # One-time cutover fallback (s5, external plan review HIGH — GLM +
        # OpenAI independently): a standalone config touched by the v1
        # update_step path BEFORE this sub-iterate has no phase_tasks[] at
        # all (only pre-existing on this developer's disk, never written
        # again going forward). Without this, promoting it to a driven run
        # silently drops its completed-phase history. Read ONLY here, at the
        # standalone->driven merge boundary, never as an ongoing reader
        # fallback — the same one-time-migration shape
        # `adopted_phase_tasks.backfill_missing_phase_tasks` already uses
        # for the analogous adopt-side gap.
        #
        # Gated on `phase_tasks_has_usable_entries`, NOT on `existing_completed`
        # being empty (external code review, GLM HIGH — the original guard
        # fired for a genuinely mid-flight v2 config too, where an empty
        # completed set is itself the authoritative answer, not an absence of
        # evidence — the same "empty vs absent" distinction s4's own fallback
        # precision-tuning already established for every other reader).
        if not phase_tasks_has_usable_entries(existing):
            legacy_completed = existing.get("completed_steps")
            if isinstance(legacy_completed, list):
                existing_completed = {s for s in legacy_completed if isinstance(s, str)}
        prior_completed = [s for s in pipeline if s in existing_completed]

    # Freeze runConditions at creation. Iterate
    # `sec-report-and-orchestrator-decouple` (2026): `securityEnabled` is
    # always False because security is no longer an orchestrator phase. We
    # still pass `aikido_client_id` so the diagnostic
    # `aikidoClientIdPresent` flag stays accurate for WebUI / CLI display.
    aikido_id = os.environ.get("AIKIDO_CLIENT_ID")
    run_conditions = freeze_run_conditions(aikido_client_id=aikido_id)

    # Initial phase_tasks[] — the "project" task is always the real,
    # CAS-ready initial task (materialized by _build_initial_phase_task,
    # whatever the state machine's own first phase is); if standalone-merge
    # already completed it, we still emit it but status=skipped, to keep the
    # audit trail clean, mirroring how a genuinely driven run marks it.
    # Any OTHER already-completed phase (a standalone run that also did
    # design/plan/... via bare phase invocations before /shipwright-run)
    # gets its own v1-shaped entry via build_v1_phase_task — it never went
    # through the CAS lifecycle, but the CAS lifecycle itself never
    # replays a phase already represented in phase_tasks[] (plan_next_phase
    # only ever inspects the single predecessor task it was just handed), so
    # this only matters for readers deriving "what already ran" from
    # phase_tasks[] (dashboard, compliance, Phase-Quality) — exactly the
    # readers that used to consult completed_steps for this.
    initial_task = _build_initial_phase_task(now_iso)
    if "project" in prior_completed:
        initial_task["status"] = "skipped"
        initial_task["completedAt"] = now_iso
        # Phase-Quality engagement (external code review, GLM MEDIUM): every
        # OTHER standalone-completed phase below gets build_v1_phase_task's
        # executionCount=1 ("done" is active); this one skips that helper
        # (it must stay the real CAS-ready task) so it needs the same stamp
        # by hand, or _task_has_run reads it as never-run and Phase-Quality
        # silently audits "project" less than its equally-completed siblings
        # now that _engagement.py's completed_steps/current_step OR-fallback
        # is gone (s5) — it genuinely ran, standalone, just before this.
        initial_task["executionCount"] = 1
    merged_tasks = [
        build_v1_phase_task(step, "done", now=now_iso)
        for step in prior_completed
        if step != "project"
    ]

    remaining = [s for s in pipeline if s not in prior_completed]

    config: dict[str, Any] = {
        # --- v2 fields ---
        "schemaVersion": SCHEMA_VERSION,
        "runId": run_id,
        # Pipeline execution mode — single_session is the sole mode, honoured by
        # the in-conversation orchestrator loop. Written explicitly (not left to a
        # reader default) because the WebUI renders this field.
        "mode": mode,
        "runConditions": run_conditions,
        "splits_frozen": [],
        "completed_phase_task_ids": [
            t["phaseTaskId"] for t in [initial_task, *merged_tasks] if t["status"] in {"done", "skipped"}
        ],
        "phase_tasks": [initial_task, *merged_tasks],
        "scope": scope,
        "profile": profile,
        "autonomy": autonomy,
        "deploy_target": deploy_target,
        "pipeline": pipeline,
        "status": "in_progress" if remaining else "complete",
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

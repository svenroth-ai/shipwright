#!/usr/bin/env python3
"""Orchestrator for shipwright-run.

Manages pipeline state: which skill runs next, progress tracking, resume support.

Usage:
    uv run orchestrator.py write-config --scope <scope> --profile <profile> --autonomy <level>
    uv run orchestrator.py get-next-step --project-root <path>
    uv run orchestrator.py update-step --project-root <path> --step <step> --status <status>

Output (JSON): config or next step info
"""

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# Add shared scripts and local lib to path for imports
_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent.parent.parent / "shared" / "scripts"
_LOCAL_LIB = str(Path(__file__).resolve().parent)
sys.path.insert(0, str(_SHARED_SCRIPTS))
if _LOCAL_LIB not in sys.path:
    sys.path.insert(0, _LOCAL_LIB)

from phase_state_machine import (  # noqa: E402
    freeze_run_conditions,
    initial_phase_spec,
)

CONFIG_NAME = "shipwright_run_config.json"

# Multi-session pipeline schema version. F2+ phase-lifecycle subcommands
# (claim-phase-task, complete-phase-task, etc.) hard-fail on anything else.
SCHEMA_VERSION = 2

# Compliance plugin location (sibling plugin)
_THIS_PLUGIN = Path(__file__).parent.parent.parent
_COMPLIANCE_SCRIPT = _THIS_PLUGIN.parent / "shipwright-compliance" / "scripts" / "tools" / "update_compliance.py"

PIPELINE_STEPS = ["project", "design", "plan", "build", "test", "changelog", "deploy"]

# Legacy pipeline entries removed by load_run_config migration. Kept for
# documentation: projects migrated off a prior pipeline get those entries
# dropped from `pipeline` (not replayed) but preserved in `completed_steps`
# as a historical marker.
#
#   "compliance" — removed earlier (plan v7 Option Z); compliance is now an
#       auto-background side-effect + on-demand /shipwright-compliance audit.
#   "security" — removed in iterate sec-report-and-orchestrator-decouple
#       (2026); security is now manual via /shipwright-security or scheduled
#       via .github/workflows/security.yml.
_LEGACY_PIPELINE_ENTRIES: frozenset[str] = frozenset({"compliance", "security"})

# Plan § 4.4 / 9.2 — Orchestrator gate Critical-Check allowlist.
# These FAILs block phase-transition only when
# ``SHIPWRIGHT_ENFORCE_CRITICAL_GATES=1`` is set. Default OFF in code.
_CRITICAL_GATE_CHECK_IDS: frozenset[str] = frozenset({"W5", "W6", "W7"})


def build_pipeline() -> list[str]:
    """Return the static orchestrator phase list.

    Iterate `sec-report-and-orchestrator-decouple` removed the conditional-
    steps mechanism: security is no longer auto-inserted after test. Run
    `/shipwright-security` manually or activate `.github/workflows/security.yml`.
    """
    return PIPELINE_STEPS.copy()


def load_run_config(project_root: Path) -> dict[str, Any]:
    """Load orchestrator config."""
    path = project_root / CONFIG_NAME
    if not path.exists():
        return {}  # Valid: first run, no config yet
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "warning": "Corrupt orchestrator config",
            "error_category": "validation",
            "what_failed": f"Parse {CONFIG_NAME}",
            "exception": str(exc),
            "alternative": "Delete the file and re-run /shipwright-run to recreate",
        }), file=sys.stderr)
        return {}
    return _migrate_legacy_pipeline_if_needed(project_root, config)


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
    save_run_config(project_root, config)
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


def save_run_config(project_root: Path, config: dict[str, Any]) -> None:
    """Save orchestrator config."""
    path = project_root / CONFIG_NAME
    config["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def is_v2_config(config: dict[str, Any]) -> bool:
    """Return True if config carries the multi-session schema (v2)."""
    return config.get("schemaVersion") == SCHEMA_VERSION


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
) -> dict[str, Any]:
    """Create initial orchestrator config (v2 multi-session schema).

    If a standalone config exists (from prior /shipwright-project or similar),
    merges its completed_steps so already-finished phases are not repeated.
    Backwards-compat note: standalone configs use the legacy v1 fields
    (current_step / completed_steps); we still merge those, but the new
    config we write is always v2 (schemaVersion: 2 + phase_tasks[]).
    """
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
        # --- v2 multi-session fields ---
        "schemaVersion": SCHEMA_VERSION,
        "runId": run_id,
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


def get_next_step(project_root: Path) -> dict[str, Any]:
    """Determine what the next pipeline step should be."""
    config = load_run_config(project_root)

    if not config:
        return {"next_step": "project", "reason": "no config found, start from beginning"}

    completed = set(config.get("completed_steps", []))
    pipeline = config.get("pipeline", PIPELINE_STEPS)

    for step in pipeline:
        if step not in completed:
            return {
                "next_step": step,
                "completed": list(completed),
                "remaining": [s for s in pipeline if s not in completed],
                "scope": config.get("scope"),
                "profile": config.get("profile"),
                "autonomy": config.get("autonomy"),
            }

    return {
        "next_step": None,
        "reason": "all steps completed",
        "completed": list(completed),
    }


def run_compliance_update(project_root: Path, phase: str) -> dict[str, Any] | None:
    """Run incremental compliance update after a phase completes.

    Returns parsed JSON output on success, None if compliance plugin not found
    or on error (non-blocking).
    """
    if not _COMPLIANCE_SCRIPT.exists():
        # Loud-fail (plan v7). Historically this branch returned None
        # silently, which hid missing-plugin installs from users.
        sys.stderr.write(json.dumps({
            "level": "warn",
            "message": "compliance update script missing",
            "path": str(_COMPLIANCE_SCRIPT),
            "phase": phase,
        }) + "\n")
        _record_compliance_update_failed(project_root, phase, reason="script_missing")
        return None

    try:
        result = subprocess.run(
            [sys.executable, str(_COMPLIANCE_SCRIPT),
             "--project-root", str(project_root),
             "--phase", phase],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
            cwd=str(project_root),
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        # Non-zero exit or empty stdout — log for diagnostics
        sys.stderr.write(json.dumps({
            "level": "warn",
            "message": f"Compliance update failed for phase '{phase}'",
            "returncode": result.returncode,
            "stderr": (result.stderr or "")[:500],
        }) + "\n")
        _record_compliance_update_failed(
            project_root, phase,
            reason=f"subprocess_exit_{result.returncode}",
        )
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(json.dumps({
            "level": "warn",
            "message": f"Compliance update error for phase '{phase}'",
            "error": str(exc),
        }) + "\n")
        _record_compliance_update_failed(
            project_root, phase, reason=f"subprocess_error:{type(exc).__name__}",
        )
    return None


def _enforce_critical_gates_enabled() -> bool:
    """Return True when SHIPWRIGHT_ENFORCE_CRITICAL_GATES opts-in.

    Default OFF in code (plan § 9.1). Rollout week 6 flips it on for
    W5/W6/W7 FAILs (plan § 9.2).
    """
    raw = os.environ.get("SHIPWRIGHT_ENFORCE_CRITICAL_GATES", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _read_latest_phase_quality_finding(
    project_root: Path, phase: str,
) -> dict[str, Any] | None:
    """Return the most recent Phase-Quality finding JSON for ``phase``.

    The Stop hook writes per-run findings to
    ``.shipwright/compliance/skill-compliance/<phase>-<run_id>-<session>.json``. We
    pick the latest by mtime so the gate reflects the current run's
    audit (plan § 4.4).
    """
    finding_dir = project_root / ".shipwright" / "compliance" / "skill-compliance"
    if not finding_dir.is_dir():
        return None

    candidates = sorted(
        finding_dir.glob(f"{phase}-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _collect_critical_gate_issues(finding: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ask-level validation issues for any critical-gate FAIL.

    A "critical" FAIL is a finding whose ``id`` is in
    ``_CRITICAL_GATE_CHECK_IDS`` with status=FAIL. SKIP/WARN/PASS are
    ignored. Tier-2 findings are never considered — critical gating is
    Tier-1 only by design (plan § 9.2).
    """
    issues: list[dict[str, Any]] = []
    for category in ("workflow", "canon", "infrastructure",
                     "traceability", "quality", "spec"):
        for item in finding.get(category, []) or []:
            if not isinstance(item, dict):
                continue
            if item.get("status") != "FAIL":
                continue
            check_id = item.get("id") or ""
            if check_id not in _CRITICAL_GATE_CHECK_IDS:
                continue
            if item.get("tier") == 2:  # safety belt — never gate Tier-2
                continue
            issues.append({
                "severity": "ask",
                "name": f"{check_id} ({category})",
                "reason": item.get("evidence") or "critical check failed",
                "remediation": item.get("remediation")
                    or "Re-run the validator or override via --force after fixing the root cause.",
            })
    return issues


def _reset_tool_counter(project_root: Path) -> None:
    """Reset tool call counter to zero (between-skill cleanup)."""
    counter = project_root / ".shipwright" / "toolcall_count"
    try:
        counter.parent.mkdir(parents=True, exist_ok=True)
        counter.write_text("0", encoding="utf-8")
    except OSError:
        pass


def update_step(project_root: Path, step: str, status: str, *, force: bool = False) -> dict[str, Any]:
    """Update a pipeline step's status.

    On completion, runs phase validation first (unless force=True or standalone).
    If validation returns ask-level issues, sets status to "needs_validation"
    and returns without marking complete. The caller (SKILL.md) should then
    ask the user and re-call with force=True if the user approves.

    On completion, also triggers incremental compliance update.
    """
    config = load_run_config(project_root)

    # Bootstrap: standalone invocation without /shipwright-run
    if not config:
        config = {
            "pipeline": build_pipeline(),
            "status": "in_progress",
            "current_step": step,
            "completed_steps": [],
            "standalone": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            # Iterate 12.0 (ADR-027): empty phase_history on bootstrap so
            # append_phase_history.py never has to synthesise the schema.
            "phase_history": {},
        }

    # Standalone configs skip interactive validation (no user to answer)
    is_standalone = config.get("standalone", False)

    if status == "complete":
        # Phase validation gate (skip for standalone — no interactive user)
        if not force and not is_standalone:
            from phase_validators import validate_phase
            valid, issues = validate_phase(step, project_root)
            ask_issues = [i for i in issues if i["severity"] == "ask"]
            inform_issues = [i for i in issues if i["severity"] == "inform"]

            # Phase-Quality critical-gate (plan § 4.4) — opt-in via
            # SHIPWRIGHT_ENFORCE_CRITICAL_GATES=1. Default OFF. Pulls the
            # most recent per-phase finding JSON written by the Stop hook
            # and promotes any W5/W6/W7 FAIL into an ask-level issue.
            if not force and _enforce_critical_gates_enabled():
                finding = _read_latest_phase_quality_finding(project_root, step)
                if finding:
                    ask_issues.extend(_collect_critical_gate_issues(finding))

            # Record inform-level notes (non-blocking)
            if inform_issues:
                notes = config.get("validation_notes", [])
                notes.extend({"step": step, **i} for i in inform_issues)
                config["validation_notes"] = notes

            # Ask-level issues: pause for user decision
            if ask_issues:
                config["current_step"] = step
                config["status"] = "needs_validation"
                config["validation_issues"] = [{"step": step, **i} for i in ask_issues]
                save_run_config(project_root, config)
                return config

        # Clear prior validation state on success/force
        config.pop("validation_issues", None)

        completed = config.get("completed_steps", [])
        if step not in completed:
            completed.append(step)
        config["completed_steps"] = completed

        # Trigger incremental compliance update (non-blocking on failure)
        compliance_result = run_compliance_update(project_root, step)

        # Split-loop: after build, check if more splits remain
        # Test/changelog/deploy run ONCE after all splits are built
        if step == "build":
            progress = get_build_progress(project_root)
            if progress.get("total_splits", 0) > 0 and not progress.get("all_done", True):
                # More splits remain — loop back to plan for next split
                split_steps = {"plan", "build"}
                config["completed_steps"] = [s for s in completed if s not in split_steps]
                config["current_step"] = "plan"
                config["status"] = "in_progress"
                if compliance_result:
                    config["last_compliance_update"] = {
                        "phase": step,
                        "reports": compliance_result.get("updated_reports", []),
                    }
                # Reset tool counter (between-skill cleanup)
                _reset_tool_counter(project_root)
                save_run_config(project_root, config)
                return config

        # Set next step
        pipeline = config.get("pipeline", PIPELINE_STEPS)
        remaining = [s for s in pipeline if s not in completed]
        config["current_step"] = remaining[0] if remaining else None
        if not remaining:
            config["status"] = "complete"

        if compliance_result:
            config["last_compliance_update"] = {
                "phase": step,
                "reports": compliance_result.get("updated_reports", []),
            }

    elif status == "in_progress":
        config["current_step"] = step

    elif status == "failed":
        config["current_step"] = step
        config["status"] = "failed"

    save_run_config(project_root, config)
    return config


def get_build_progress(project_root: Path) -> dict[str, Any]:
    """Return section-level progress for the build phase.

    Reads shipwright_build_config.json and returns counts plus the next
    section to work on.  Used by the orchestrator autopilot loop and the
    resume-detection logic in SKILL.md.

    Returns split-aware progress:
        split_done: all sections in current split are complete
        all_done: entire build is done (all splits complete)
    """
    from lib.config import collect_all_build_sections

    build_info = collect_all_build_sections(project_root)

    # Current split sections (what the agent works on)
    sections = build_info["current"]
    completed = [s for s in sections if s.get("status") == "complete"]
    in_progress = [s for s in sections if s.get("status") == "in_progress"]
    pending = [s for s in sections if s.get("status") not in ("complete", "in_progress", "failed")]

    # Next section: first in_progress (resume), else first pending
    next_section = None
    if in_progress:
        next_section = in_progress[0]
    elif pending:
        next_section = pending[0]

    # Split awareness
    split_done = len(sections) > 0 and len(completed) == len(sections)
    completed_splits = build_info["completed_splits"]
    total_splits = build_info["total_splits"]

    # all_done: split_done AND no more splits remain
    # For single-split projects (total_splits <= 1), split_done == all_done
    if total_splits > 0:
        all_done = split_done and (len(completed_splits) + 1 >= total_splits)
    else:
        all_done = split_done

    # Total across all splits (for dashboard reporting)
    all_sections = build_info["all"]
    total_all = len(all_sections)
    completed_all = sum(1 for s in all_sections if s.get("status") == "complete")

    return {
        "total": len(sections),
        "completed": len(completed),
        "in_progress": len(in_progress),
        "completed_sections": [s.get("name") for s in completed],
        "next_section": next_section.get("name") if next_section else None,
        "split_done": split_done,
        "all_done": all_done,
        "current_split": build_info["current_split"],
        "completed_splits": completed_splits,
        "total_splits": total_splits,
        "total_all": total_all,
        "completed_all": completed_all,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("write-config")
    p.add_argument("--scope", required=True, choices=["full_app", "extension"])
    p.add_argument("--profile", default=None)
    p.add_argument("--autonomy", default="guided", choices=["guided", "autonomous"])
    p.add_argument("--deploy-target", default="jelastic-dev")
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser("get-next-step")
    p.add_argument("--project-root", default=".")

    p = subparsers.add_parser("update-step")
    p.add_argument("--project-root", default=".")
    # Iterate sec-report-and-orchestrator-decouple removed CONDITIONAL_STEPS
    # ("security"). Legacy phase_tasks with phase=security are still accepted
    # so users running update-step on an in-flight upgraded run aren't blocked.
    all_steps = PIPELINE_STEPS + ["security"]
    p.add_argument("--step", required=True, choices=all_steps)
    p.add_argument("--status", required=True, choices=["in_progress", "complete", "failed"])
    p.add_argument("--force", action="store_true", help="Skip validation (user override)")

    p = subparsers.add_parser("get-build-progress")
    p.add_argument("--project-root", default=".")

    # ----- F2 phase-task lifecycle subcommands ---------------------------
    # All return JSON on stdout. Exit codes:
    #   0 = ok
    #   1 = generic error (not_found, invalid args)
    #   2 = fail-closed (block) — used by phase_session_start.py / phase_user_prompt_validate.py

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

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if args.command == "write-config":
        config = create_config(
            args.scope, args.profile, args.autonomy,
            args.deploy_target, project_root,
        )
        print(json.dumps(config, indent=2))

    elif args.command == "get-next-step":
        result = get_next_step(project_root)
        print(json.dumps(result, indent=2))

    elif args.command == "update-step":
        config = update_step(project_root, args.step, args.status, force=args.force)
        print(json.dumps(config, indent=2))

    elif args.command == "get-build-progress":
        result = get_build_progress(project_root)
        print(json.dumps(result, indent=2))

    # ----- F2 lifecycle subcommand dispatch ------------------------------
    elif args.command in {
        "get-phase-task", "find-phase-task-by-session-uuid",
        "validate-prerequisites", "claim-phase-task", "complete-phase-task",
        "mark-phase-failed", "recover-phase-task", "freeze-splits",
        "plan-next-phase",
    }:
        return _dispatch_lifecycle(args, project_root)

    return 0


def _dispatch_lifecycle(args: argparse.Namespace, project_root: Path) -> int:
    """Run an F2 phase-lifecycle subcommand. Returns process exit code.

    Exit code map:
        0 -> result["ok"] is True
        2 -> fail-closed reasons (wrong_skill, duplicate_claim,
             phase_already_terminal, prereqs_unmet, stale_version,
             stale_session) — used by hooks for SessionStart/UserPromptSubmit blocks
        1 -> generic error (not_found, invalid args, etc.)
    """
    from phase_task_lifecycle import (  # noqa: WPS433 (lazy import keeps F1 base import surface clean)
        claim_phase_task,
        complete_phase_task,
        find_phase_task_by_session_uuid,
        freeze_splits,
        get_phase_task,
        mark_phase_failed,
        plan_next_phase,
        recover_phase_task,
        validate_prerequisites,
    )

    fail_closed_reasons = frozenset({
        "wrong_skill", "duplicate_claim", "phase_already_terminal",
        "prereqs_unmet", "stale_version", "stale_session",
        "invalid_status", "invalid_status_for_completion",
    })

    cmd = args.command
    result: dict[str, Any]
    if cmd == "get-phase-task":
        result = get_phase_task(project_root, args.phase_task_id)
    elif cmd == "find-phase-task-by-session-uuid":
        found = find_phase_task_by_session_uuid(project_root, args.session_uuid)
        result = {"ok": True, "phase_task": found} if found else {"ok": False, "reason": "not_found"}
    elif cmd == "validate-prerequisites":
        result = validate_prerequisites(project_root, args.phase_task_id)
    elif cmd == "claim-phase-task":
        result = claim_phase_task(
            project_root,
            phase_task_id=args.phase_task_id,
            session_uuid=args.session_uuid,
            expected_phase=args.expected_phase,
        )
    elif cmd == "complete-phase-task":
        result_path = Path(args.result_json)
        if not result_path.exists():
            print(json.dumps({"ok": False, "reason": "result_json_not_found",
                              "path": str(result_path)}), file=sys.stderr)
            return 1
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(json.dumps({"ok": False, "reason": "result_json_parse_error",
                              "error": str(exc)}), file=sys.stderr)
            return 1
        result = complete_phase_task(
            project_root,
            phase_task_id=args.phase_task_id,
            session_uuid=args.session_uuid,
            expected_version=args.version,
            result=payload,
        )
    elif cmd == "mark-phase-failed":
        result = mark_phase_failed(
            project_root,
            phase_task_id=args.phase_task_id,
            session_uuid=args.session_uuid,
            expected_version=args.version,
            error=args.error,
        )
    elif cmd == "recover-phase-task":
        result = recover_phase_task(
            project_root,
            phase_task_id=args.phase_task_id,
            force_status=args.force_status,
        )
    elif cmd == "freeze-splits":
        result = freeze_splits(project_root)
    elif cmd == "plan-next-phase":
        result = plan_next_phase(
            project_root, completed_phase_task_id=args.phase_task_id,
        )
    else:
        # Unreachable — argparse already validates choices
        print(json.dumps({"ok": False, "reason": "unknown_command", "command": cmd}),
              file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if result.get("ok"):
        return 0
    if result.get("reason") in fail_closed_reasons:
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())

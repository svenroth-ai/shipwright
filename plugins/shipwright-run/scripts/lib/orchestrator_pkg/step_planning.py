"""Step-planning + update for the orchestrator package.

Holds ``get_next_step`` (what phase runs next?) and ``update_step``
(mark a phase in_progress/complete/failed). ``update_step`` is the only
function that talks to ``run_compliance_update``; it does so via the
``orchestrator`` shim namespace so tests' ``mocker.patch(
"orchestrator.run_compliance_update")`` works after the B5 split.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .build_progress import get_build_progress
from .config_factory import build_pipeline
from .config_io import load_run_config, save_run_config
from .constants import PIPELINE_STEPS
from .critical_gates import (
    _collect_critical_gate_issues,
    _enforce_critical_gates_enabled,
    _read_latest_phase_quality_finding,
)


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


def _reset_tool_counter(project_root: Path) -> None:
    """Reset tool call counter to zero (between-skill cleanup)."""
    counter = project_root / ".shipwright" / "toolcall_count"
    try:
        counter.parent.mkdir(parents=True, exist_ok=True)
        counter.write_text("0", encoding="utf-8")
    except OSError:
        pass


def _run_compliance_update(project_root: Path, phase: str) -> dict[str, Any] | None:
    """Indirection so tests can patch ``orchestrator.run_compliance_update``.

    Late lookup through ``sys.modules["orchestrator"]`` honors the mock
    binding set by ``mocker.patch("orchestrator.run_compliance_update", ...)``.
    Fallback: import the package binding directly.
    """
    shim = sys.modules.get("orchestrator")
    if shim is not None and hasattr(shim, "run_compliance_update"):
        return shim.run_compliance_update(project_root, phase)
    from .compliance_runner import run_compliance_update
    return run_compliance_update(project_root, phase)


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
        compliance_result = _run_compliance_update(project_root, step)

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

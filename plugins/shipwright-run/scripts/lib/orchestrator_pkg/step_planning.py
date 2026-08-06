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
from pathlib import Path
from typing import Any

from .build_progress import get_build_progress
# No tolerant ``load_run_config`` import here, deliberately: every read in this
# module can advance or change a run, so the strict reader is the only one in
# scope. Pinned by test_no_mutating_path_reaches_a_tolerant_read.
from .config_io import RunConfigUnreadable, read_run_config, save_run_config
from .constants import PIPELINE_STEPS
# The two strict chokepoints update_step reads through. Re-exported into this
# namespace because callers and tests reach them as
# ``step_planning._read_standalone_flag`` / ``._load_or_bootstrap``.
from .step_config_access import (  # noqa: F401
    _bootstrap_standalone_config,
    _load_or_bootstrap,
    _read_standalone_flag,
)
from .validation_record import (
    normalise_override_reason,
    record_inform_notes,
    record_validation_override,
    run_phase_gate,
)

# ``run_config_store`` is a top-level module in this plugin's scripts/lib;
# the ``.constants`` import above already put that dir on sys.path.
from run_config_store import run_config_lock  # noqa: E402


def get_next_step(project_root: Path) -> dict[str, Any]:
    """Determine what the next pipeline step should be.

    A reporter, so an unusable config must not make it CRASH — but it must stop
    it LYING: it answered "no config found, start from beginning" for a truncated
    config recording two completed phases. ``blocked`` distinguishes that refusal
    from all-steps-complete, which also carries ``next_step: None``.
    """
    try:
        config, present = read_run_config(project_root)
    except RunConfigUnreadable as exc:
        return {"next_step": None, "blocked": True, **exc.payload()}

    # `not config` alone, deliberately: `_read_parse_shape` returns `({}, False)`
    # for absent, so a `not present` clause could never decide anything on its
    # own. A PRESENT-but-empty `{}` shares this answer ON PURPOSE — unlike
    # `_load_or_bootstrap`, which must not overwrite it, a reporter asked "what
    # runs next?" about a config recording no pipeline and no completed steps has
    # nothing to resume, so "start from the beginning" is the true answer here.
    if not config:
        return {"next_step": "project", "reason": "no config found, start from beginning"}

    # `or`, not a .get default: an EXPLICIT null passes the shape gate (it is a
    # well-formed object) and would then raise TypeError out of a reporter that
    # promises not to crash. `update_step` already tolerates it the same way.
    completed = set(config.get("completed_steps") or [])
    pipeline = config.get("pipeline") or PIPELINE_STEPS

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


def update_step(
    project_root: Path,
    step: str,
    status: str,
    *,
    force: bool = False,
    force_reason: str | None = None,
) -> dict[str, Any]:
    """Update a pipeline step's status.

    On completion, runs phase validation first (unless standalone). If validation
    returns ask-level issues, sets status to "needs_validation" and returns
    without marking complete. The caller (SKILL.md) should then ask the user and
    re-call with force=True — plus ``force_reason`` — if the user approves.

    **``force`` overrides the VERDICT, never the CHECK** (FR-01.01). The gate runs
    either way; what force changes is that ask-level findings no longer pause the
    run. What the gate said, and the reason the person gave for going ahead, are
    written to ``validation_overrides[]`` so that afterwards "passed its checks"
    and "was waved through" can still be told apart. Before this, force skipped
    ``validate_phase`` entirely and the two were indistinguishable.

    ``force_reason`` is mandatory whenever ``force`` completes a non-standalone
    step; a blank one raises ``ValueError`` before anything is read or written.

    On completion, also triggers incremental compliance update.

    Concurrency (audit WP2/F11): the slow read-only work (``validate_phase`` +
    the compliance subprocess) runs OUTSIDE the advisory run-config lock; only
    the read-modify-write — reload a FRESH config, apply this function's own
    fields, atomic-save — runs UNDER the lock. So a concurrent ``phase_task``
    / ``phase_history`` write (which touches different fields) is never
    clobbered by a stale in-memory copy, and the lock is never held across the
    ~30 s subprocess.
    """
    # Read the standalone flag WITHOUT migrating (the migration write would be
    # UNLOCKED here, before the run_config_lock below). The in-lock
    # _load_or_bootstrap reloads still perform the migration under the lock.
    is_standalone = _read_standalone_flag(project_root)

    if status == "complete":
        ask_issues: list[dict[str, Any]] = []
        inform_issues: list[dict[str, Any]] = []
        gate_checked = True

        # Phase validation gate (skip for standalone — no interactive user, so
        # there is nobody to override and nothing was overridden). Reads project
        # artifacts, not the run config, so it runs unlocked.
        if not is_standalone:
            # Refuse a reasonless override BEFORE running or writing anything, so
            # a malformed call cannot half-complete a phase.
            if force:
                force_reason = normalise_override_reason(force_reason)

            # ALWAYS runs — including under force. That is the fix: an override
            # must not erase the finding it overrode.
            ask_issues, inform_issues, gate_checked = run_phase_gate(project_root, step)

            # Ask-level issues without an override: pause for a user decision
            # (persist under lock).
            if ask_issues and not force:
                with run_config_lock(project_root):
                    config = _load_or_bootstrap(project_root, step)
                    record_inform_notes(config, step, inform_issues)
                    config["current_step"] = step
                    config["status"] = "needs_validation"
                    config["validation_issues"] = [{"step": step, **i} for i in ask_issues]
                    save_run_config(project_root, config)
                    return config

        # Trigger incremental compliance update (non-blocking on failure).
        # Up to a 30 s subprocess — kept OUTSIDE the lock (F11).
        compliance_result = _run_compliance_update(project_root, step)

        with run_config_lock(project_root):
            config = _load_or_bootstrap(project_root, step)
            # Clear BOTH halves of an earlier unforced attempt's pause, so a
            # completed step never carries state implying it is still stuck. The
            # findings alone were not enough: `status` stayed "needs_validation"
            # while `completed_steps` and `current_step` had moved on, and that
            # key is what update_build_dashboard and resolve_next_dispatch read.
            # The terminal assignment below still overrides this when the
            # pipeline is finished.
            # Clear only THIS step's pause — both halves of it, together.
            #
            # `needs_validation` has a second producer: phase_task_lifecycle
            # writes it to mean "deploy completed while other phase tasks are
            # still non-terminal", and resolve_next_dispatch branches on it. The
            # two are mode-disjoint at the CLI (the drivability guard), but
            # update_step() has no such guard, so lifting that pause here would be
            # the halt-a-healthy-run failure the guard exists to prevent.
            #
            # The issues are filtered by the SAME predicate as the status. An
            # earlier version popped every issue while lifting only a matching
            # pause, which left a run parked in `needs_validation` with nothing
            # left on disk to say why — the dashboard then rendered a paused run
            # with no reason.
            issues = config.get("validation_issues") or []
            mine = [i for i in issues if isinstance(i, dict) and i.get("step") == step]
            theirs = [i for i in issues if i not in mine]
            if theirs:
                config["validation_issues"] = theirs
            else:
                config.pop("validation_issues", None)
            if mine and config.get("status") == "needs_validation":
                config["status"] = "in_progress"
            record_inform_notes(config, step, inform_issues)
            if force and not is_standalone:
                record_validation_override(
                    config, step, reason=force_reason,
                    ask_issues=ask_issues, inform_issues=inform_issues,
                    checked=gate_checked,
                )

            completed = config.get("completed_steps", [])
            if step not in completed:
                completed.append(step)
            config["completed_steps"] = completed

            # Split-loop: after build, loop back to plan if more splits remain
            # (test/changelog/deploy run ONCE after all splits are built).
            if step == "build":
                progress = get_build_progress(project_root)
                if progress.get("total_splits", 0) > 0 and not progress.get("all_done", True):
                    split_steps = {"plan", "build"}
                    config["completed_steps"] = [s for s in completed if s not in split_steps]
                    config["current_step"] = "plan"
                    config["status"] = "in_progress"
                    _record_compliance_result(config, step, compliance_result)
                    _reset_tool_counter(project_root)
                    save_run_config(project_root, config)
                    return config

            pipeline = config.get("pipeline") or PIPELINE_STEPS  # tolerate explicit null
            remaining = [s for s in pipeline if s not in completed]
            config["current_step"] = remaining[0] if remaining else None
            if not remaining:
                config["status"] = "complete"
            _record_compliance_result(config, step, compliance_result)
            save_run_config(project_root, config)
            return config

    # in_progress / failed (and any other status): quick locked RMW, no
    # compliance/validation, so nothing slow runs under the lock.
    with run_config_lock(project_root):
        config = _load_or_bootstrap(project_root, step)
        if status == "in_progress":
            config["current_step"] = step
        elif status == "failed":
            config["current_step"] = step
            config["status"] = "failed"
        save_run_config(project_root, config)
        return config


def _record_compliance_result(
    config: dict[str, Any], step: str, compliance_result: dict[str, Any] | None,
) -> None:
    """Stamp ``last_compliance_update`` from a non-None compliance result, in place."""
    if compliance_result:
        config["last_compliance_update"] = {
            "phase": step,
            "reports": compliance_result.get("updated_reports", []),
        }

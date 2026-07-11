#!/usr/bin/env python3
"""Stop hook for the multi-session pipeline (F3a).

Wired into all 8 phase plugins. Runs FIRST in the Stop hook chain, before
generate_handoff_on_stop.py, so phase_tasks[] is updated by the time the
handoff file is written.

Identity (project_root + session_id) is resolved from the hook **stdin payload**
via ``lib.hook_session`` (NOT process env vars that no launcher sets —
ADR-092/097, deep-audit F1).

Behaviour:
    1. Discover the active phase_task by matching the payload session_id against
       phase_tasks[].sessionUuid. No match -> standalone, exit 0.
    2. Read the validation marker (sessionstart-validation.json) to know our
       claimed version. If valid=false (block was active), don't try to
       complete — just exit 0.
    3. Collect the result payload from the phase-specific config
       (shipwright_<phase>_config.json). Defensive: missing/corrupt -> ok=false
       so the lifecycle helper routes to mark_phase_failed.
    4. If phase == design AND result.ok: call freeze-splits BEFORE
       complete-phase-task so splits_frozen is populated when the design->plan
       successor is materialised.
    5. Call complete-phase-task. If it returns stale_session/stale_version
       (owner+version-CAS rejected us): write a stale_stop_rejected event and
       exit 0 — the pipeline state is already correctly protected.
    6. Record phase_completed (or phase_failed) event in shipwright_events.jsonl
       via record_event.py.

Exit code: always 0 unless something genuinely fatal happens — the Stop hook
should never crash the session shutdown.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


_THIS = Path(__file__).resolve()
_SHARED_SCRIPTS = _THIS.parent.parent  # shared/scripts (for lib.hook_session)
_RUN_LIB = _THIS.parent.parent.parent.parent / "plugins" / "shipwright-run" / "scripts" / "lib"
_SHARED_TOOLS = _SHARED_SCRIPTS / "tools"
sys.path.insert(0, str(_RUN_LIB))
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

try:
    from phase_task_lifecycle import (  # type: ignore[import]
        complete_phase_task,
        find_phase_task_by_session_uuid,
        freeze_splits,
    )
except ImportError:  # pragma: no cover
    complete_phase_task = None
    find_phase_task_by_session_uuid = None
    freeze_splits = None

# Hook stdin-payload resolution (deep-audit F1). Guarded so a broken install
# degrades to standalone rather than crashing the Stop hook.
try:
    from lib.hook_session import resolve_hook_context  # type: ignore[import]
except ImportError:  # pragma: no cover - import-path safety
    resolve_hook_context = None


CONFIG_NAME = "shipwright_run_config.json"


# ---------------------------------------------------------------------------
# Result collection
# ---------------------------------------------------------------------------

PHASE_CONFIG_NAME = {
    "project": "shipwright_project_config.json",
    "design": "shipwright_design_config.json",
    "plan": "shipwright_plan_config.json",
    "build": "shipwright_build_config.json",
    "test": "shipwright_test_results.json",
    "security": None,  # No dedicated config — security writes a markdown report
    "changelog": None,  # CHANGELOG.md is the artifact
    "deploy": "shipwright_deploy_config.json",
}


def collect_result(project_root: Path, phase: str) -> dict[str, Any]:
    """Read the phase's config to derive {ok, ...} for complete-phase-task.

    Defensive: missing/corrupt/no-config-defined -> ok=true (assume the phase
    completed normally) for security/changelog which have no canonical config.
    Missing/corrupt for phases that DO have a config -> ok=false with reason.
    """
    cfg_name = PHASE_CONFIG_NAME.get(phase)
    if cfg_name is None:
        # Phases without a config file — trust the session ended normally
        return {"ok": True, "phase": phase, "note": "no_canonical_config"}

    path = project_root / cfg_name
    if not path.exists():
        return {
            "ok": False, "phase": phase,
            "reason": f"missing_or_corrupt_config:{cfg_name}",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "ok": False, "phase": phase,
            "reason": f"config_parse_error:{exc}",
        }

    # Honour explicit ok flag if the phase wrote one
    if "ok" in data:
        return {"ok": bool(data["ok"]), "phase": phase, "config": cfg_name,
                **({"reason": data.get("reason")} if not data.get("ok") else {})}
    # Otherwise: presence of the config file is success enough
    return {"ok": True, "phase": phase, "config": cfg_name,
            "status": data.get("status")}


# ---------------------------------------------------------------------------
# Event recording (best-effort)
# ---------------------------------------------------------------------------

def _record_event(project_root: Path, event_type: str, phase: str,
                  extra: Optional[dict[str, Any]] = None) -> None:
    """Append an event via record_event.py. Never raises."""
    record_script = _SHARED_TOOLS / "record_event.py"
    if not record_script.exists():
        return
    args = [
        sys.executable, str(record_script),
        "--project-root", str(project_root),
        "--type", event_type,
        "--phase", phase,
    ]
    if extra:
        args.extend(["--detail", json.dumps(extra)])
        # Promote the splitId the caller already carries in `extra` to a
        # top-level --split-id so phase_completed dedups by (phase, splitId): a
        # multi-split phase records one end per split rather than collapsing to
        # the first (iterate-2026-07-11-phase-completed-per-split).
        split_id = extra.get("splitId")
        if split_id is not None:  # forward any explicit splitId (None = single-pass phase)
            args.extend(["--split-id", str(split_id)])
    try:
        subprocess.run(args, capture_output=True, text=True, timeout=10)
    except (subprocess.TimeoutExpired, OSError):
        pass


# ---------------------------------------------------------------------------
# Validation marker (set by phase_session_start.py)
# ---------------------------------------------------------------------------

def _read_validation(project_root: Path, run_id: str, phase_task_id: str) -> Optional[dict[str, Any]]:
    target = (
        project_root / ".shipwright" / "runs" / run_id / phase_task_id
        / "sessionstart-validation.json"
    )
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(project_root: Optional[Path], session_uuid: Optional[str]) -> int:
    """Pure entry point. Returns exit code."""
    if project_root is None or session_uuid is None:
        return 0
    if find_phase_task_by_session_uuid is None or complete_phase_task is None:
        return 0

    config_path = project_root / CONFIG_NAME
    if not config_path.exists():
        return 0
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    if config.get("schemaVersion") != 2:
        return 0

    task = find_phase_task_by_session_uuid(project_root, session_uuid)
    if task is None:
        return 0  # standalone

    phase_task_id = task["phaseTaskId"]
    phase = task["phase"]
    run_id = config.get("runId", "unknown-run")

    validation = _read_validation(project_root, run_id, phase_task_id)
    if validation is None:
        # No validation marker -> SessionStart hook didn't run (or our config
        # was changed). Skip — we don't have a trustworthy version number.
        return 0
    if not validation.get("valid", False):
        # We were blocked. Don't try to complete the task.
        return 0

    expected_version = int(validation.get("version", task.get("version", 1)))

    # Collect result payload
    result = collect_result(project_root, phase)

    # Special case: design phase freezes splits BEFORE its completion is
    # finalised, so the design->plan successor sees splits_frozen.
    if phase == "design" and result.get("ok") and freeze_splits is not None:
        try:
            freeze_splits(project_root)
        except Exception as exc:  # noqa: BLE001  - never crash the stop hook
            sys.stderr.write(f"[phase_session_stop] freeze_splits failed: {exc}\n")

    # Owner-checked complete (routes to mark_phase_failed internally if ok=false)
    completion = complete_phase_task(
        project_root,
        phase_task_id=phase_task_id,
        session_uuid=session_uuid,
        expected_version=expected_version,
        result=result,
    )

    if not completion.get("ok"):
        reason = completion.get("reason", "unknown")
        # stale_session / stale_version means another session has taken
        # ownership (e.g. via recover-phase-task) — record diagnostic and
        # exit cleanly.
        _record_event(project_root, "stale_stop_rejected", phase, {
            "phaseTaskId": phase_task_id,
            "reason": reason,
            "actual_version": completion.get("actual_version"),
            "expected_version": completion.get("expected_version"),
        })
        sys.stderr.write(
            f"[phase_session_stop] stop rejected ({reason}); "
            f"task ownership has moved.\n",
        )
        return 0

    # Record success/failure event
    final_status = completion["phase_task"].get("status")
    event_type = "phase_failed" if final_status == "failed" else "phase_completed"
    _record_event(project_root, event_type, phase, {
        "phaseTaskId": phase_task_id,
        "splitId": task.get("splitId"),
        "next_phase_task": (
            completion.get("next_phase_task") if isinstance(completion.get("next_phase_task"), dict)
            else None
        ),
        "run_status": completion.get("run_status"),
    })
    return 0


def main() -> int:
    if resolve_hook_context is None:
        return 0  # helper unavailable — degrade to standalone, never crash
    project_root, session_uuid = resolve_hook_context()
    return run(project_root, session_uuid)


if __name__ == "__main__":
    sys.exit(main())

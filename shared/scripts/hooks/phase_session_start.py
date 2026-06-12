#!/usr/bin/env python3
"""SessionStart hook for the multi-session pipeline (F3a).

Wired into all 8 phase plugins. Resolves ``(project_root, session_id)`` from the
hook **stdin payload** via ``lib.hook_session`` — NOT from process env vars that
no launcher sets (ADR-092/097, deep-audit F1). The payload always carries
``session_id`` + ``cwd``; ``resolve_project_root()`` is the fallback.

Behaviour (Plan v4 + Mini-Spike findings):

    1. If the project root can't be resolved, OR no shipwright_run_config.json,
       OR config is not v2 -> standalone, exit 0 silently.

    2. Otherwise: identify our phase from CLAUDE_PLUGIN_ROOT (e.g.
       'shipwright-build' -> 'build'). Match SHIPWRIGHT_SESSION_ID against
       phase_tasks[].sessionUuid.

    3. No match -> standalone (user pasted command without a claim), exit 0
       silently. The skill runs in standalone mode.

    4. Match found -> validate:
        - Wrong skill (expected_phase != claimed_phase): block
        - Status terminal: block
        - Status in_progress with different claimer: block (duplicate)
        - Prereqs unmet: block
       Block path: write .block-pending sentinel + sessionstart-validation.json
       with valid=false + blockMessage. SessionStart cannot stop execution
       (Spike F0 finding), so we let the matching UserPromptSubmit hook
       (phase_user_prompt_validate.py) read the marker and emit
       decision=block on the first user prompt.

    5. All checks pass -> claim_phase_task (CAS). Then write
       sessionstart-validation.json with valid=true and emit additionalContext
       so the Skill's Step 0 can parse phaseTaskId and load context.

Exit codes: always 0 (SessionStart can't block). Block decisions are
deferred to the UserPromptSubmit hook via .block-pending.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional


_THIS = Path(__file__).resolve()
_SHARED_SCRIPTS = _THIS.parent.parent  # shared/scripts (for lib.hook_session)
_RUN_LIB = _THIS.parent.parent.parent.parent / "plugins" / "shipwright-run" / "scripts" / "lib"
sys.path.insert(0, str(_RUN_LIB))
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

# Lazy-imported on demand; tests stub these.
try:
    from phase_task_lifecycle import (  # type: ignore[import]
        PLUGIN_PHASE_MAP,
        claim_phase_task,
        find_phase_task_by_session_uuid,
        validate_prerequisites,
    )
except ImportError:  # pragma: no cover - import-path safety
    PLUGIN_PHASE_MAP = {}
    claim_phase_task = None
    find_phase_task_by_session_uuid = None
    validate_prerequisites = None

# Hook stdin-payload resolution (deep-audit F1). Guarded so a broken install
# degrades to standalone rather than crashing SessionStart.
try:
    from lib.hook_session import resolve_hook_context  # type: ignore[import]
except ImportError:  # pragma: no cover - import-path safety
    resolve_hook_context = None


CONFIG_NAME = "shipwright_run_config.json"


def _emit_additional_context(text: str) -> None:
    """Emit a hookSpecificOutput payload so the LLM sees ``text``.

    Spike F0 finding: must use hookSpecificOutput.additionalContext schema.
    Top-level additionalContext is silently ignored.
    """
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }
    sys.stdout.write(json.dumps(payload) + "\n")


def _identify_plugin_phase(plugin_root: Optional[str]) -> Optional[str]:
    """Map CLAUDE_PLUGIN_ROOT (e.g. .../shipwright-build) -> phase name."""
    if not plugin_root:
        return None
    name = Path(plugin_root).name
    return PLUGIN_PHASE_MAP.get(name)


def _task_dir(project_root: Path, run_id: str, phase_task_id: str) -> Path:
    d = project_root / ".shipwright" / "runs" / run_id / phase_task_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_validation(
    project_root: Path, run_id: str, phase_task_id: str, payload: dict[str, Any],
) -> None:
    target = _task_dir(project_root, run_id, phase_task_id) / "sessionstart-validation.json"
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_block_pending(
    project_root: Path, run_id: str, phase_task_id: str, message: str,
) -> None:
    """Write the single-use sentinel for phase_user_prompt_validate.py.

    The UserPromptSubmit hook reads this on first fire and deletes it so
    follow-up prompts in the same session pass through (Spike F0 mini-finding).
    """
    target = _task_dir(project_root, run_id, phase_task_id) / ".block-pending"
    target.write_text(message, encoding="utf-8")


def _build_pipeline_context_block(task: dict[str, Any], config: dict[str, Any]) -> str:
    rc = config.get("runConditions") or {}
    prereqs = task.get("prerequisites") or []
    prereqs_str = ",".join(f"{pid}=?" for pid in prereqs) or "(none)"
    return (
        "=== SHIPWRIGHT-PIPELINE-CONTEXT ===\n"
        f"runId: {config.get('runId')}\n"
        f"phaseTaskId: {task['phaseTaskId']}\n"
        f"phase: {task['phase']}\n"
        f"splitId: {task.get('splitId')}\n"
        f"version: {task.get('version')}\n"
        f"prerequisites: {prereqs_str}\n"
        f"runConditions: securityEnabled={rc.get('securityEnabled')} "
        f"splitMode={rc.get('splitMode')}\n"
        "\n"
        "REQUIRED: As your very first action, run:\n"
        f"  uv run ${{SHIPWRIGHT_PLUGIN_ROOT}}/../../shared/scripts/tools/get_phase_context.py "
        f"--phase-task-id {task['phaseTaskId']}\n"
        "\n"
        "Read the artifacts the tool surfaces (skill_artifacts_to_read) "
        "before proceeding with normal Step 1.\n"
        "=== END PIPELINE-CONTEXT ===\n"
    )


def _build_block_context_block(message: str) -> str:
    return (
        "=== SHIPWRIGHT-PIPELINE-CONTEXT (BLOCKED) ===\n"
        f"{message}\n"
        "\n"
        "STOP — your launch parameters are inconsistent with the active "
        "shipwright-run pipeline. Refuse to proceed. The next user prompt "
        "will be hard-blocked by the UserPromptSubmit hook anyway.\n"
        "=== END PIPELINE-CONTEXT ===\n"
    )


def run(project_root: Path, session_uuid: Optional[str], plugin_root: Optional[str]) -> int:
    """Pure-callable entry point. Returns the exit code main() will use."""
    if not project_root or not session_uuid:
        return 0  # pre-conditions not met -> standalone

    config_path = project_root / CONFIG_NAME
    if not config_path.exists():
        return 0  # standalone (no run config)

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0  # standalone (corrupt config — don't crash skills)

    if config.get("schemaVersion") != 2:
        return 0  # standalone (legacy v1 config)

    # Discovery
    task = find_phase_task_by_session_uuid(project_root, session_uuid)
    if task is None:
        return 0  # session_uuid not in phase_tasks[] -> standalone

    phase_task_id = task["phaseTaskId"]
    run_id = config.get("runId", "unknown-run")
    expected_phase = _identify_plugin_phase(plugin_root)

    # Wrong-skill check (Spike F0 finding: SessionStart can't actually block,
    # so we write the marker and let UserPromptSubmit do the block).
    if expected_phase and task["phase"] != expected_phase:
        msg = (
            f"Session UUID claimed for phase '{task['phase']}' but launched "
            f"under plugin for phase '{expected_phase}'. Either re-launch with "
            f"the correct slash command (/shipwright-{task['phase']}), or call "
            f"recover-phase-task to release the UUID."
        )
        _write_validation(project_root, run_id, phase_task_id, {
            "valid": False, "reason": "wrong_skill",
            "expected_phase": expected_phase, "claimed_phase": task["phase"],
            "phaseTaskId": phase_task_id, "runId": run_id,
            "blockMessage": msg,
        })
        _write_block_pending(project_root, run_id, phase_task_id, msg)
        _emit_additional_context(_build_block_context_block(msg))
        return 0

    # Status check
    status = task.get("status")
    claimed_by = task.get("claimedBySessionUuid")
    if status in {"done", "failed", "skipped"}:
        msg = (
            f"Phase task {phase_task_id} is in terminal status '{status}'. "
            f"Use orchestrator.py recover-phase-task to release it before "
            f"re-launching."
        )
        _write_validation(project_root, run_id, phase_task_id, {
            "valid": False, "reason": "phase_already_terminal",
            "status": status, "phaseTaskId": phase_task_id, "runId": run_id,
            "blockMessage": msg,
        })
        _write_block_pending(project_root, run_id, phase_task_id, msg)
        _emit_additional_context(_build_block_context_block(msg))
        return 0

    if status == "in_progress" and claimed_by and claimed_by != session_uuid:
        msg = (
            f"Phase task {phase_task_id} is already claimed by another "
            f"session ({claimed_by!r}). Duplicate launch detected."
        )
        _write_validation(project_root, run_id, phase_task_id, {
            "valid": False, "reason": "duplicate_claim",
            "claimed_by": claimed_by, "phaseTaskId": phase_task_id, "runId": run_id,
            "blockMessage": msg,
        })
        _write_block_pending(project_root, run_id, phase_task_id, msg)
        _emit_additional_context(_build_block_context_block(msg))
        return 0

    # Prereq check
    prereq_check = validate_prerequisites(project_root, phase_task_id)
    if not prereq_check.get("ok", False):
        msg = prereq_check.get("blockMessage", "prerequisites unmet")
        _write_validation(project_root, run_id, phase_task_id, {
            "valid": False, "reason": "prereqs_unmet",
            "prereqs_status": prereq_check.get("prereqs_status"),
            "phaseTaskId": phase_task_id, "runId": run_id,
            "blockMessage": msg,
        })
        _write_block_pending(project_root, run_id, phase_task_id, msg)
        _emit_additional_context(_build_block_context_block(msg))
        return 0

    # Happy path — claim (idempotent on re-entry)
    claim = claim_phase_task(
        project_root,
        phase_task_id=phase_task_id,
        session_uuid=session_uuid,
        expected_phase=task["phase"],
    )
    if not claim.get("ok", False):
        msg = claim.get("blockMessage", "claim failed")
        _write_validation(project_root, run_id, phase_task_id, {
            "valid": False, "reason": claim.get("reason", "claim_failed"),
            "phaseTaskId": phase_task_id, "runId": run_id,
            "blockMessage": msg,
        })
        _write_block_pending(project_root, run_id, phase_task_id, msg)
        _emit_additional_context(_build_block_context_block(msg))
        return 0

    # Write success validation (no .block-pending marker).
    claimed_task = claim["phase_task"]
    _write_validation(project_root, run_id, phase_task_id, {
        "valid": True, "reason": "ok",
        "phaseTaskId": phase_task_id, "runId": run_id,
        "phase": claimed_task["phase"],
        "splitId": claimed_task.get("splitId"),
        "version": claimed_task["version"],
        "claimedBySessionUuid": claimed_task["claimedBySessionUuid"],
        "idempotent": claim.get("idempotent", False),
    })
    _emit_additional_context(_build_pipeline_context_block(claimed_task, config))
    return 0


def main() -> int:
    if resolve_hook_context is None:
        return 0  # helper unavailable — degrade to standalone, never crash
    project_root, session_uuid = resolve_hook_context()
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return run(project_root, session_uuid, plugin_root)


if __name__ == "__main__":
    sys.exit(main())

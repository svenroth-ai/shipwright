"""SHIPWRIGHT-PIPELINE-CONTEXT block builders for phase_session_start.

Pure string builders extracted from ``phase_session_start.py`` (to keep that hook
under the 300-LOC guideline): they format the ``additionalContext`` blocks the
SessionStart hook emits to the model — the normal pipeline-context block on a
successful phase claim, and the BLOCKED variant when a launch is rejected.
"""

from __future__ import annotations

from typing import Any


def build_pipeline_context_block(task: dict[str, Any], config: dict[str, Any]) -> str:
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


def build_block_context_block(message: str) -> str:
    return (
        "=== SHIPWRIGHT-PIPELINE-CONTEXT (BLOCKED) ===\n"
        f"{message}\n"
        "\n"
        "STOP — your launch parameters are inconsistent with the active "
        "shipwright-run pipeline. Refuse to proceed. The next user prompt "
        "will be hard-blocked by the UserPromptSubmit hook anyway.\n"
        "=== END PIPELINE-CONTEXT ===\n"
    )

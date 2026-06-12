#!/usr/bin/env python3
"""UserPromptSubmit hook for the multi-session pipeline (F3a).

Spike F0 finding: SessionStart hooks cannot block skill execution. To
fail-closed wrong-skill / duplicate-claim / phase-already-terminal /
prereqs-unmet conditions, the SessionStart hook (phase_session_start.py)
writes a single-use sentinel `.block-pending` into the phase task's
`.shipwright/runs/<runId>/<phaseTaskId>/` directory.

Mini-spike finding: UserPromptSubmit fires per-prompt (not per-session,
also after `--resume`). The sentinel must be deleted on first read so
follow-up prompts in the same session pass through normally.

Behaviour:
    1. Discover the active phase_task via SHIPWRIGHT_SESSION_ID -> sessionUuid.
    2. If no match (standalone) -> exit 0 silently.
    3. Look for .block-pending in the task directory.
    4. If present: read message, DELETE it (single-use), emit
       hookSpecificOutput.additionalContext + decision=block + exit 2.
    5. If absent: exit 0 (pass-through). Either it was already consumed,
       or no block was needed.

Exit 2 + decision=block prevents the LLM from processing this prompt.
Subsequent prompts will see no marker -> pass through.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


_THIS = Path(__file__).resolve()
_SHARED_SCRIPTS = _THIS.parent.parent  # shared/scripts (for lib.hook_session)
_RUN_LIB = _THIS.parent.parent.parent.parent / "plugins" / "shipwright-run" / "scripts" / "lib"
sys.path.insert(0, str(_RUN_LIB))
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

try:
    from phase_task_lifecycle import find_phase_task_by_session_uuid  # type: ignore[import]
except ImportError:  # pragma: no cover
    find_phase_task_by_session_uuid = None

# Hook stdin-payload resolution (deep-audit F1). Guarded so a broken install
# degrades to pass-through rather than crashing UserPromptSubmit.
try:
    from lib.hook_session import resolve_hook_context  # type: ignore[import]
except ImportError:  # pragma: no cover - import-path safety
    resolve_hook_context = None


CONFIG_NAME = "shipwright_run_config.json"


def _block_pending_path(
    project_root: Path, run_id: str, phase_task_id: str,
) -> Path:
    return (
        project_root / ".shipwright" / "runs" / run_id / phase_task_id / ".block-pending"
    )


def run(project_root: Optional[Path], session_uuid: Optional[str]) -> int:
    """Pure-callable entry point. Returns process exit code."""
    if project_root is None or session_uuid is None:
        return 0  # standalone

    if find_phase_task_by_session_uuid is None:
        return 0  # safety net — lifecycle lib unavailable

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
        return 0  # standalone — session not in pipeline

    run_id = config.get("runId", "unknown-run")
    marker = _block_pending_path(project_root, run_id, task["phaseTaskId"])
    if not marker.exists():
        return 0  # pass-through

    # Single-use consume: read message, then unlink before emitting.
    try:
        message = marker.read_text(encoding="utf-8").strip()
    except OSError:
        message = "shipwright-run pipeline detected an inconsistent launch."

    try:
        marker.unlink()
    except OSError:
        # If we can't delete, we'd loop-block. Log to stderr but proceed
        # with the block — the user can manually delete the file if stuck.
        sys.stderr.write(
            f"[phase_user_prompt_validate] WARN: could not delete {marker}\n",
        )

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "=== SHIPWRIGHT-PIPELINE-BLOCK ===\n"
                f"{message}\n"
                "=== END BLOCK ==="
            ),
        },
        "decision": "block",
        "reason": "shipwright-run pipeline phase-claim violation",
    }
    sys.stdout.write(json.dumps(payload) + "\n")
    return 2


def main() -> int:
    if resolve_hook_context is None:
        return 0  # helper unavailable — pass through, never crash
    project_root, session_uuid = resolve_hook_context()
    return run(project_root, session_uuid)


if __name__ == "__main__":
    sys.exit(main())

"""Cross-component integration: the Stop hook's real subprocess call into
``update-step`` seeds ``phase_tasks[]`` on disk, and the UserPromptSubmit
router then reads that SAME fresh signal instead of its own legacy cutover.

``generate_handoff_on_stop.py`` and ``suggest_iterate.py`` (both touched by
sub-iterate s5) each carry a UNIT-tested one-time legacy cutover in
isolation (``test_generate_handoff_on_stop.py``,
``test_suggest_iterate.py``) -- but those tests stub out the real producer
(``_run_phase_completion``) that the Stop hook's cutover exists to trigger.
This test drives the REAL end-to-end seam: a genuinely legacy (no
``phase_tasks[]``) standalone config, run through the actual
``generate_handoff_on_stop.py`` subprocess (which shells out to the real
``orchestrator.py update-step`` CLI), and the resulting on-disk config fed
into ``suggest_iterate.handle_in_progress_pipeline`` -- proving the two
hook modules compose through the real writer, not merely that each one's
own fallback branch is reachable in isolation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from hooks.suggest_iterate import handle_in_progress_pipeline  # noqa: E402

_HOOK_SCRIPT = _SCRIPTS_ROOT / "hooks" / "generate_handoff_on_stop.py"


def _run_stop_hook(cwd: Path) -> subprocess.CompletedProcess:
    """Run the real Stop-hook subprocess, mimicking Claude Code's invocation."""
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_RUN_ID", None)  # never take the canon-marker skip path
    return subprocess.run(
        [sys.executable, str(_HOOK_SCRIPT)],
        input="{}", capture_output=True, text=True, cwd=cwd, env=env, timeout=120,
    )


def test_stop_hook_seeds_phase_tasks_that_suggest_iterate_then_prefers_over_legacy(
    tmp_path,
):
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    # `standalone: True` skips update_step's interactive validation gate
    # (no real project/design/plan/build artifacts exist here) the same
    # way a real standalone run would have been marked. `current_step`
    # deliberately picks "test" (not "plan"/"build") to avoid
    # _detect_phase_complete's unrelated split-loop-resume guard.
    run_config = {
        "standalone": True,
        "status": "in_progress",
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
        "current_step": "test",
        "completed_steps": ["project", "design", "plan", "build"],
    }
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps(run_config), encoding="utf-8",
    )
    # Makes _detect_phase_complete("test", ...) report True, so the Stop
    # hook's fallback actually calls _run_phase_completion -> the real CLI.
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"status": "pass"}), encoding="utf-8",
    )

    result = _run_stop_hook(tmp_path)
    assert result.returncode == 0, result.stderr

    updated = json.loads(
        (tmp_path / "shipwright_run_config.json").read_text(encoding="utf-8"),
    )
    phase_tasks = updated.get("phase_tasks")
    assert isinstance(phase_tasks, list) and phase_tasks, (
        "the Stop hook's one-time cutover should have driven the real "
        "`update-step` CLI, which seeds phase_tasks[] on disk"
    )
    test_tasks = [t for t in phase_tasks if t.get("phase") == "test"]
    assert test_tasks and test_tasks[0].get("status") == "done"

    # Feed suggest_iterate the SAME on-disk config, prompting about "test"
    # again. A wrongly-consulted legacy read would see current_step="test"
    # (matching the prompt's detected intent) and stay silent. The real
    # phase_tasks[]-first read reports NO current phase (test just
    # finished, nothing beyond it ever claimed) -- an intent/step mismatch
    # -- proving suggest_iterate consumed the fresh signal the Stop hook's
    # real subprocess call just wrote, not the stale legacy fields still
    # sitting (unchanged) on this same dict.
    output = handle_in_progress_pipeline(
        "run the tests now please", tmp_path, updated,
    )
    assert output is not None, (
        "a legacy-field read would have matched current_step='test' "
        "against the detected 'test' intent and stayed silent"
    )
    message = output["hookSpecificOutput"]["additionalContext"]
    assert "pipeline is at step 'unknown'" in message, message

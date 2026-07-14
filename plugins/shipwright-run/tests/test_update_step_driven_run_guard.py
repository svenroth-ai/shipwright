"""The `update-step` CLI must be INERT inside a driven single-session run.

This guard exists because of a near-miss in iterate-2026-07-14-phase-invocation-mode.

`update-step` is the **v1** completion path. In a v2 driven run `single-session-apply` owns
phase completion, and `plugins/shipwright-run/skills/run/SKILL.md` says so plainly:
*"Do NOT ... call `orchestrator update-step`. The loop's two subcommands are the only way
phases advance."* But that was enforced by PROSE alone, while the phase skills' completion
steps (`build/references/section-state.md`, `test/references/step-5-report-results.md`, …)
invoke `orchestrator.py update-step` unconditionally, as does the
`generate_handoff_on_stop` Stop-hook fallback.

It stayed harmless only by accident: the phase skills misclassified themselves as
*standalone* — they keyed on the never-advanced v1 `current_step` — and the standalone
branch says "skip pipeline state updates". Fixing that misclassification (the point of that
iterate) would have made every driven phase start calling `update-step` FOR REAL, and:

    update_step() -> validate_phase() -> any ask-level issue
                  -> config["status"] = "needs_validation"

is the SAME key `single_session_loop.resolve_next_dispatch` reads *before* the phase_tasks
frontier. One ask-level issue (e.g. a split with no unit tests) would halt a structurally
healthy run — permanently: nothing resets `needs_validation` back to `in_progress`
(`--force` only skips the ask branch; `recover_phase_task` only lifts `failed`).

The guard is at the **CLI boundary**, not in `update_step()`: every real caller reaches the
command there, while the state-machine FUNCTION stays intact for standalone / legacy /
adopted runs (and its own unit tests). So a driven run cannot be wedged by a phase skill no
matter what any prose says, and the v1 machine keeps working where it legitimately runs.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
SCRIPT = str(_LIB / "orchestrator.py")

CONFIG = "shipwright_run_config.json"


def _write(project_root: Path, config: dict) -> None:
    (project_root / CONFIG).write_text(json.dumps(config), encoding="utf-8")


def _driven_config(status: str = "in_progress") -> dict:
    return {
        "schemaVersion": 2, "mode": "single_session", "status": status,
        "current_step": "project", "completed_steps": [], "pipeline": ["project", "test"],
        "phase_tasks": [], "runConditions": {},
    }


def _run_update_step(project_root: Path, step: str, status: str) -> dict:
    """Invoke the CLI exactly as a phase skill / the Stop hook does."""
    proc = subprocess.run(
        [sys.executable, SCRIPT, "update-step", "--project-root", str(project_root),
         "--step", step, "--status", status],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_driven_run_update_step_cli_never_mutates_run_state(tmp_project):
    _write(tmp_project, _driven_config())
    before = (tmp_project / CONFIG).read_text(encoding="utf-8")

    result = _run_update_step(tmp_project, "test", "complete")

    assert result["driven_run"] is True
    assert result["state_mutated"] is False
    assert (tmp_project / CONFIG).read_text(encoding="utf-8") == before


def test_driven_run_cannot_be_wedged_into_needs_validation(tmp_project):
    """The exact failure scenario end-to-end: a `test` phase completion with no unit
    results emits an ask-level issue in the v1 path. The CLI guard must never let that
    reach `status = needs_validation`."""
    _write(tmp_project, _driven_config())
    # A test phase with no results file is exactly what `_validate_test` flags "ask".
    result = _run_update_step(tmp_project, "test", "complete")

    assert result["state_mutated"] is False
    config = json.loads((tmp_project / CONFIG).read_text(encoding="utf-8"))
    assert config["status"] == "in_progress", (
        "a driven run was wedged into needs_validation by an update-step call"
    )
    assert "validation_issues" not in config


def test_mode_less_config_is_not_driven_and_keeps_the_v1_path(tmp_project):
    """Drivability is EXPLICIT-LITERAL-ONLY. A config nobody is driving must still take the
    v1 path — the guard must not disable update-step for standalone / adopted / v1 runs."""
    config = _driven_config()
    del config["mode"]
    _write(tmp_project, config)

    # in_progress doesn't hit the validation gate, so the v1 advance is observable.
    result = _run_update_step(tmp_project, "build", "in_progress")

    assert result.get("driven_run") is not True
    # v1 path ran: it returned the real config and advanced the state machine.
    assert "phase_tasks" in result
    assert result.get("current_step") == "build"


def test_no_run_config_is_not_driven(tmp_project):
    result = _run_update_step(tmp_project, "project", "complete")
    assert result.get("driven_run") is not True


@pytest.mark.parametrize("status", ["in_progress", "failed", "complete"])
def test_all_statuses_are_inert_in_a_driven_run(tmp_project, status):
    _write(tmp_project, _driven_config())
    before = (tmp_project / CONFIG).read_text(encoding="utf-8")

    result = _run_update_step(tmp_project, "build", status)

    assert result["driven_run"] is True
    assert (tmp_project / CONFIG).read_text(encoding="utf-8") == before

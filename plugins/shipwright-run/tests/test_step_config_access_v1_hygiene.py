"""Regressions from external code review on the v1 phase_tasks[] advance/reset
helpers (campaign p4-04-retire-write-once-steps, sub-iterate s5, Step 3.7).

GLM (independently, twice) and OpenAI (independently) reviewed the actual
diff and found:

1. (OpenAI, medium) The `needs_validation` pause branch in `update_step`
   dropped the `current_step = step` write it replaced with nothing --
   leaving a phase paused for validation unrepresented in `phase_tasks[]`,
   the sole progress record now.
2. (GLM, low) `_upsert_v1_phase_task` left a stale `completedAt` when a task
   moved BACK to a non-terminal status (e.g. a retry after "failed").
3. (GLM, low) `_reset_v1_phase_tasks` left `startedAt` set on an entry reset
   to "awaiting_launch".
4. (GLM, low, round 2) `_upsert_v1_phase_task` treated "skipped" as
   NON-terminal when deciding `completedAt` -- unreachable via `update_step`
   today, but the helper is exported and tested as a general API.

All four fixed in `step_config_access.py` / `step_planning.py`; pinned here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config, update_step  # noqa: E402
from orchestrator_pkg.step_config_access import (  # noqa: E402
    _find_v1_phase_task,
    _reset_v1_phase_tasks,
    _upsert_v1_phase_task,
)

from tests.conftest import _phase_status  # noqa: E402


@pytest.fixture
def run_project(tmp_project, mocker):
    """A non-standalone run the v1 completion path can advance (mode stripped)."""
    mocker.patch("orchestrator.run_compliance_update", return_value=None)
    create_config(
        scope="full_app", profile="supabase-nextjs", autonomy="guided",
        deploy_target="jelastic-dev", project_root=tmp_project,
    )
    path = tmp_project / "shipwright_run_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    del config["mode"]
    path.write_text(json.dumps(config), encoding="utf-8")
    return tmp_project


def test_a_validation_pause_still_locates_the_phase_in_phase_tasks(run_project, mocker):
    mocker.patch(
        "phase_validators.validate_phase",
        return_value=(False, [{"severity": "ask", "message": "Missing spec.md"}]),
    )
    paused = update_step(run_project, "project", "complete")

    assert paused["status"] == "needs_validation"
    assert _phase_status(paused, "project") == "in_progress"


def test_retrying_a_failed_task_back_to_in_progress_clears_stale_completed_at():
    config = {"phase_tasks": []}
    _upsert_v1_phase_task(config, "build", "failed", now="2026-09-10T00:00:00Z")
    task = _find_v1_phase_task(config, "build")
    assert task["completedAt"] == "2026-09-10T00:00:00Z"

    _upsert_v1_phase_task(config, "build", "in_progress", now="2026-09-10T00:01:00Z")
    task = _find_v1_phase_task(config, "build")
    assert task["status"] == "in_progress"
    assert task["completedAt"] is None


def test_skipped_status_sets_completed_at_like_other_terminal_statuses():
    config = {"phase_tasks": []}
    _upsert_v1_phase_task(config, "test", "skipped", now="2026-09-10T00:02:00Z")
    task = _find_v1_phase_task(config, "test")
    assert task["completedAt"] == "2026-09-10T00:02:00Z"


def test_resetting_a_phase_clears_started_at_too():
    config = {"phase_tasks": []}
    _upsert_v1_phase_task(config, "plan", "in_progress", now="2026-09-10T00:00:00Z")
    task = _find_v1_phase_task(config, "plan")
    assert task["startedAt"] == "2026-09-10T00:00:00Z"

    _reset_v1_phase_tasks(config, {"plan"})
    task = _find_v1_phase_task(config, "plan")
    assert task["status"] == "awaiting_launch"
    assert task["completedAt"] is None
    assert task["startedAt"] is None

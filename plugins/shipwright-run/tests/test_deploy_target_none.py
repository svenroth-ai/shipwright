"""deploy_target "none": the pipeline ends after changelog (no Deploy phase)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config  # noqa: E402
from phase_state_machine import next_phase_task  # noqa: E402
from phase_task_lifecycle import claim_phase_task, complete_phase_task, freeze_splits  # noqa: E402

_RC = {"securityEnabled": False, "splitMode": None, "aikidoClientIdPresent": False}


def _completed(phase):
    return {"phaseTaskId": "ptk-x", "phase": phase, "splitId": None, "status": "done"}


@pytest.mark.covers("FR-01.01/AC01")
def test_changelog_is_terminal_when_deploy_disabled():
    assert next_phase_task(run_conditions=_RC, splits_frozen=[],
                           completed=_completed("changelog"), deploy_enabled=False) is None


@pytest.mark.covers("FR-01.01/AC01")
def test_changelog_still_schedules_deploy_by_default():
    spec = next_phase_task(run_conditions=_RC, splits_frozen=[], completed=_completed("changelog"))
    assert spec is not None and spec["phase"] == "deploy"


@pytest.mark.covers("FR-01.01/AC01")
def test_build_pipeline_drops_deploy_for_none_target():
    from orchestrator_pkg.config_factory import build_pipeline

    assert "deploy" not in build_pipeline("none")
    assert build_pipeline("none")[-1] == "changelog"
    assert build_pipeline("jelastic-dev")[-1] == "deploy"
    assert build_pipeline()[-1] == "deploy"


def _cfg(root: Path) -> dict:
    return json.loads((root / "shipwright_run_config.json").read_text("utf-8"))


@pytest.mark.covers("FR-01.01/AC01")
def test_deploy_target_none_completes_run_after_changelog(tmp_project, monkeypatch):
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    create_config(scope="full_app", profile="python-plugin-monorepo",
                  autonomy="guided", deploy_target="none", project_root=tmp_project)
    freeze_splits(tmp_project)
    for phase in ["project", "design", "plan", "build", "test", "changelog"]:
        cur = next(t for t in _cfg(tmp_project)["phase_tasks"]
                   if t["phase"] == phase and t["status"] == "awaiting_launch")
        sid = cur["sessionUuid"]
        claimed = claim_phase_task(tmp_project, phase_task_id=cur["phaseTaskId"],
                                   session_uuid=sid, expected_phase=phase)
        assert claimed["ok"], claimed
        res = complete_phase_task(tmp_project, phase_task_id=cur["phaseTaskId"],
                                  session_uuid=sid,
                                  expected_version=claimed["phase_task"]["version"],
                                  result={"ok": True})
        assert res["ok"], res

    cfg = _cfg(tmp_project)
    assert cfg["status"] == "complete"
    assert all(t["phase"] != "deploy" for t in cfg["phase_tasks"])

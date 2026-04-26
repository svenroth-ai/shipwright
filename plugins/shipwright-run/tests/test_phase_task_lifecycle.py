"""Tests for phase_task_lifecycle — F2 CAS-protected state transitions.

Coverage matrix (Plan v4 §F2 acceptance criteria):

    claim_phase_task:
        - happy path
        - idempotent re-entry (same session)
        - wrong-skill (expected_phase != task.phase) -> fail-closed
        - duplicate claim (different session)
        - phase already terminal -> fail-closed
        - not found

    complete_phase_task:
        - happy path -> next phase materialised
        - result.ok=False routes to mark_phase_failed
        - deploy + all terminal -> run.status=complete
        - deploy + others non-terminal -> run.status=needs_validation
        - stale_version (caller has v1, task at v2 after recover)
        - stale_session (different uuid)
        - idempotent (same owner+version twice)

    mark_phase_failed:
        - happy
        - stale version

    recover_phase_task:
        - default (awaiting_launch) -> bumps version, clears claim
        - failed / skipped force_status
        - skipped adds to completed_phase_task_ids
        - resets run.status from failed -> in_progress
        - invalid force_status

    validate_prerequisites:
        - all done -> ok with snapshot
        - non-terminal prereq -> fail-closed
        - missing prereq -> fail-closed

    freeze_splits:
        - design config wins
        - design empty list -> splitMode=none
        - design missing -> falls back to project
        - both missing/corrupt -> splits_frozen=[], warning
        - dict-shape splits

    plan_next_phase:
        - happy: project done -> design materialised
        - deploy done -> pipeline_terminal=True
        - idempotent: existing matching task -> reused
        - predecessor not found
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config  # noqa: E402
from phase_task_lifecycle import (  # noqa: E402
    claim_phase_task,
    complete_phase_task,
    find_phase_task_by_session_uuid,
    freeze_splits,
    get_phase_task,
    mark_phase_failed,
    plan_next_phase,
    recover_phase_task,
    validate_prerequisites,
)


# ---- Fixtures ----


@pytest.fixture
def v2_project(tmp_project, monkeypatch):
    """v2 config with one project task in awaiting_launch."""
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    create_config(
        scope="full_app", profile="supabase-nextjs",
        autonomy="guided", deploy_target="jelastic-dev",
        project_root=tmp_project,
    )
    return tmp_project


def _read_cfg(project_root: Path) -> dict:
    return json.loads((project_root / "shipwright_run_config.json").read_text("utf-8"))


def _project_task_id(project_root: Path) -> str:
    return _read_cfg(project_root)["phase_tasks"][0]["phaseTaskId"]


def _session_uuid(project_root: Path, task_id: str) -> str:
    cfg = _read_cfg(project_root)
    for t in cfg["phase_tasks"]:
        if t["phaseTaskId"] == task_id:
            return t["sessionUuid"]
    raise KeyError(task_id)


# ---- claim_phase_task ----


def test_claim_happy_path(v2_project):
    tid = _project_task_id(v2_project)
    sid = _session_uuid(v2_project, tid)
    res = claim_phase_task(v2_project, phase_task_id=tid, session_uuid=sid, expected_phase="project")
    assert res["ok"] is True
    t = res["phase_task"]
    assert t["status"] == "in_progress"
    assert t["claimedBySessionUuid"] == sid
    assert t["startedAt"] is not None
    assert t["executionCount"] == 1


def test_claim_idempotent_reentry_same_session(v2_project):
    tid = _project_task_id(v2_project)
    sid = _session_uuid(v2_project, tid)
    claim_phase_task(v2_project, phase_task_id=tid, session_uuid=sid, expected_phase="project")
    res = claim_phase_task(v2_project, phase_task_id=tid, session_uuid=sid, expected_phase="project")
    assert res["ok"] is True
    assert res.get("idempotent") is True
    # executionCount NOT bumped on idempotent re-entry
    assert res["phase_task"]["executionCount"] == 1


def test_claim_wrong_skill_fail_closed(v2_project):
    tid = _project_task_id(v2_project)
    sid = _session_uuid(v2_project, tid)
    res = claim_phase_task(v2_project, phase_task_id=tid, session_uuid=sid, expected_phase="build")
    assert res["ok"] is False
    assert res["reason"] == "wrong_skill"
    assert "build" in res["blockMessage"] and "project" in res["blockMessage"]
    assert res["expected_phase"] == "build"
    assert res["claimed_phase"] == "project"


def test_claim_duplicate_different_session_fail_closed(v2_project):
    tid = _project_task_id(v2_project)
    sid = _session_uuid(v2_project, tid)
    claim_phase_task(v2_project, phase_task_id=tid, session_uuid=sid, expected_phase="project")
    res = claim_phase_task(
        v2_project, phase_task_id=tid, session_uuid="other-uuid", expected_phase="project",
    )
    assert res["ok"] is False
    assert res["reason"] == "duplicate_claim"


def test_claim_phase_terminal_fail_closed(v2_project):
    tid = _project_task_id(v2_project)
    sid = _session_uuid(v2_project, tid)
    claim_phase_task(v2_project, phase_task_id=tid, session_uuid=sid, expected_phase="project")
    # Forcibly mark done
    cfg = _read_cfg(v2_project)
    cfg["phase_tasks"][0]["status"] = "done"
    (v2_project / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")

    res = claim_phase_task(v2_project, phase_task_id=tid, session_uuid=sid, expected_phase="project")
    assert res["ok"] is False
    assert res["reason"] == "phase_already_terminal"


def test_claim_not_found(v2_project):
    res = claim_phase_task(
        v2_project, phase_task_id="ptk-bogus", session_uuid="x", expected_phase="project",
    )
    assert res["ok"] is False
    assert res["reason"] == "not_found"


# ---- complete_phase_task ----


def _claim(project_root: Path, task_id: str, expected_phase: str) -> tuple[str, int]:
    sid = _session_uuid(project_root, task_id)
    res = claim_phase_task(
        project_root, phase_task_id=task_id, session_uuid=sid, expected_phase=expected_phase,
    )
    assert res["ok"], res
    return sid, res["phase_task"]["version"]


def test_complete_happy_creates_next_phase_task(v2_project):
    tid = _project_task_id(v2_project)
    sid, ver = _claim(v2_project, tid, "project")
    res = complete_phase_task(
        v2_project, phase_task_id=tid, session_uuid=sid, expected_version=ver,
        result={"ok": True, "artifacts": [".shipwright/planning/requirements.md"]},
    )
    assert res["ok"] is True
    assert res["phase_task"]["status"] == "done"
    assert res["next_phase_task"] is not None
    assert res["next_phase_task"]["phase"] == "design"
    assert tid in res["next_phase_task"]["prerequisites"]

    cfg = _read_cfg(v2_project)
    assert tid in cfg["completed_phase_task_ids"]
    phases = [t["phase"] for t in cfg["phase_tasks"]]
    assert phases == ["project", "design"]


def test_complete_with_ok_false_routes_to_failed(v2_project):
    tid = _project_task_id(v2_project)
    sid, ver = _claim(v2_project, tid, "project")
    res = complete_phase_task(
        v2_project, phase_task_id=tid, session_uuid=sid, expected_version=ver,
        result={"ok": False, "reason": "spec generation crashed"},
    )
    assert res["ok"] is True  # the helper succeeded
    assert res["phase_task"]["status"] == "failed"
    assert "spec generation crashed" in res["phase_task"]["errors"]
    cfg = _read_cfg(v2_project)
    assert cfg["status"] == "failed"
    # No next phase planned
    assert len(cfg["phase_tasks"]) == 1


def test_complete_idempotent_same_owner_version(v2_project):
    tid = _project_task_id(v2_project)
    sid, ver = _claim(v2_project, tid, "project")
    a = complete_phase_task(
        v2_project, phase_task_id=tid, session_uuid=sid, expected_version=ver,
        result={"ok": True},
    )
    b = complete_phase_task(
        v2_project, phase_task_id=tid, session_uuid=sid, expected_version=ver,
        result={"ok": True},
    )
    assert a["ok"] and b["ok"]
    assert b.get("idempotent") is True
    cfg = _read_cfg(v2_project)
    assert len([t for t in cfg["phase_tasks"] if t["phase"] == "design"]) == 1


def test_complete_stale_version_after_recover(v2_project):
    tid = _project_task_id(v2_project)
    sid, ver = _claim(v2_project, tid, "project")
    # Sim crash + recover
    rec = recover_phase_task(v2_project, phase_task_id=tid, force_status="awaiting_launch")
    assert rec["ok"] and rec["new_version"] == ver + 1

    # Old session (with old version) tries to complete -> stale
    res = complete_phase_task(
        v2_project, phase_task_id=tid, session_uuid=sid, expected_version=ver,
        result={"ok": True},
    )
    assert res["ok"] is False
    assert res["reason"] == "stale_version"
    assert res["actual_version"] == ver + 1


def test_complete_stale_session_different_uuid(v2_project):
    tid = _project_task_id(v2_project)
    sid, ver = _claim(v2_project, tid, "project")
    res = complete_phase_task(
        v2_project, phase_task_id=tid, session_uuid="not-the-claimer",
        expected_version=ver, result={"ok": True},
    )
    assert res["ok"] is False
    assert res["reason"] == "stale_session"


def test_complete_deploy_with_all_terminal_sets_run_complete(v2_project):
    """Walk the full pipeline (no per-split splits, security disabled)."""
    # Disable per-split entirely by freezing with no splits
    freeze_splits(v2_project)  # design+project configs missing -> none
    cfg = _read_cfg(v2_project)
    assert cfg["runConditions"]["splitMode"] == "none"

    # Walk: project -> design -> plan -> build -> test -> changelog -> deploy
    expected = ["project", "design", "plan", "build", "test", "changelog", "deploy"]
    for phase in expected:
        cur = next(t for t in _read_cfg(v2_project)["phase_tasks"]
                   if t["phase"] == phase and t["status"] == "awaiting_launch")
        sid, ver = _claim(v2_project, cur["phaseTaskId"], phase)
        res = complete_phase_task(
            v2_project, phase_task_id=cur["phaseTaskId"], session_uuid=sid,
            expected_version=ver, result={"ok": True},
        )
        assert res["ok"], res

    assert _read_cfg(v2_project)["status"] == "complete"


def test_complete_deploy_with_other_non_terminal_sets_needs_validation(v2_project):
    """Walk to deploy, then secretly add a stuck phase_task before completing."""
    freeze_splits(v2_project)
    for phase in ["project", "design", "plan", "build", "test", "changelog"]:
        cur = next(t for t in _read_cfg(v2_project)["phase_tasks"]
                   if t["phase"] == phase and t["status"] == "awaiting_launch")
        sid, ver = _claim(v2_project, cur["phaseTaskId"], phase)
        complete_phase_task(
            v2_project, phase_task_id=cur["phaseTaskId"], session_uuid=sid,
            expected_version=ver, result={"ok": True},
        )

    # Inject an orphaned in_progress task BEFORE deploy completes
    cfg = _read_cfg(v2_project)
    cfg["phase_tasks"].append({
        "phaseTaskId": "ptk-orphan", "phase": "test", "splitId": None,
        "sessionUuid": "orphan-uuid", "version": 1, "status": "in_progress",
        "title": "orphan", "slashCommand": "/shipwright-test", "prerequisites": [],
        "claimedBySessionUuid": "x", "claimAttemptedAt": None,
        "executionCount": 1, "createdAt": "z", "awaitingLaunchAt": None,
        "startedAt": "z", "completedAt": None, "result": None, "errors": [],
    })
    (v2_project / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")

    deploy = next(t for t in cfg["phase_tasks"] if t["phase"] == "deploy" and t["status"] == "awaiting_launch")
    sid, ver = _claim(v2_project, deploy["phaseTaskId"], "deploy")
    res = complete_phase_task(
        v2_project, phase_task_id=deploy["phaseTaskId"], session_uuid=sid,
        expected_version=ver, result={"ok": True},
    )

    assert res["ok"] is True
    assert res["run_status"] == "needs_validation"
    assert "pipeline_completion_blocked" in res
    blocked_ids = [b["phaseTaskId"] for b in res["pipeline_completion_blocked"]]
    assert "ptk-orphan" in blocked_ids
    assert _read_cfg(v2_project)["status"] == "needs_validation"


# ---- mark_phase_failed ----


def test_mark_failed_happy(v2_project):
    tid = _project_task_id(v2_project)
    sid, ver = _claim(v2_project, tid, "project")
    res = mark_phase_failed(
        v2_project, phase_task_id=tid, session_uuid=sid,
        expected_version=ver, error="boom",
    )
    assert res["ok"] is True
    assert res["phase_task"]["status"] == "failed"
    assert "boom" in res["phase_task"]["errors"]
    assert _read_cfg(v2_project)["status"] == "failed"


def test_mark_failed_stale_version_rejected(v2_project):
    tid = _project_task_id(v2_project)
    sid, ver = _claim(v2_project, tid, "project")
    recover_phase_task(v2_project, phase_task_id=tid, force_status="awaiting_launch")
    res = mark_phase_failed(
        v2_project, phase_task_id=tid, session_uuid=sid,
        expected_version=ver, error="too late",
    )
    assert res["ok"] is False
    assert res["reason"] == "stale_version"


# ---- recover_phase_task ----


def test_recover_default_to_awaiting_launch_bumps_version(v2_project):
    tid = _project_task_id(v2_project)
    sid, ver = _claim(v2_project, tid, "project")
    res = recover_phase_task(v2_project, phase_task_id=tid)
    assert res["ok"] is True
    assert res["new_version"] == ver + 1
    t = res["phase_task"]
    assert t["status"] == "awaiting_launch"
    assert t["claimedBySessionUuid"] is None
    assert t["startedAt"] is None
    assert t["awaitingLaunchAt"] is not None


def test_recover_force_failed(v2_project):
    tid = _project_task_id(v2_project)
    res = recover_phase_task(v2_project, phase_task_id=tid, force_status="failed")
    assert res["ok"] is True
    assert res["phase_task"]["status"] == "failed"


def test_recover_force_skipped_adds_to_completed_ids(v2_project):
    tid = _project_task_id(v2_project)
    res = recover_phase_task(v2_project, phase_task_id=tid, force_status="skipped")
    assert res["ok"] is True
    assert res["phase_task"]["status"] == "skipped"
    assert tid in _read_cfg(v2_project)["completed_phase_task_ids"]


def test_recover_resets_run_status_when_was_failed(v2_project):
    tid = _project_task_id(v2_project)
    sid, ver = _claim(v2_project, tid, "project")
    mark_phase_failed(v2_project, phase_task_id=tid, session_uuid=sid,
                      expected_version=ver, error="x")
    assert _read_cfg(v2_project)["status"] == "failed"

    recover_phase_task(v2_project, phase_task_id=tid, force_status="awaiting_launch")
    assert _read_cfg(v2_project)["status"] == "in_progress"


def test_recover_invalid_force_status(v2_project):
    tid = _project_task_id(v2_project)
    res = recover_phase_task(v2_project, phase_task_id=tid, force_status="bogus")
    assert res["ok"] is False
    assert res["reason"] == "invalid_force_status"


# ---- validate_prerequisites ----


def test_validate_prereqs_all_done(v2_project):
    tid = _project_task_id(v2_project)
    sid, ver = _claim(v2_project, tid, "project")
    complete_phase_task(v2_project, phase_task_id=tid, session_uuid=sid,
                        expected_version=ver, result={"ok": True})

    design_id = next(t for t in _read_cfg(v2_project)["phase_tasks"]
                     if t["phase"] == "design")["phaseTaskId"]
    res = validate_prerequisites(v2_project, design_id)
    assert res["ok"] is True
    assert res["prereqs_status"] == [{"phaseTaskId": tid, "status": "done"}]


def test_validate_prereqs_non_terminal_fails_closed(v2_project):
    tid = _project_task_id(v2_project)
    _claim(v2_project, tid, "project")  # in_progress, not done
    # Manually create a successor task pointing at this prereq
    cfg = _read_cfg(v2_project)
    cfg["phase_tasks"].append({
        "phaseTaskId": "ptk-design-fake", "phase": "design", "splitId": None,
        "sessionUuid": "x", "version": 1, "status": "awaiting_launch",
        "title": "design", "slashCommand": "/shipwright-design",
        "prerequisites": [tid], "claimedBySessionUuid": None,
        "claimAttemptedAt": None, "executionCount": 0, "createdAt": "z",
        "awaitingLaunchAt": "z", "startedAt": None, "completedAt": None,
        "result": None, "errors": [],
    })
    (v2_project / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")

    res = validate_prerequisites(v2_project, "ptk-design-fake")
    assert res["ok"] is False
    assert res["reason"] == "prereqs_unmet"
    assert "in_progress" in res["blockMessage"]


def test_validate_prereqs_missing(v2_project):
    cfg = _read_cfg(v2_project)
    cfg["phase_tasks"].append({
        "phaseTaskId": "ptk-orphan", "phase": "design", "splitId": None,
        "sessionUuid": "x", "version": 1, "status": "awaiting_launch",
        "title": "design", "slashCommand": "/shipwright-design",
        "prerequisites": ["ptk-doesnotexist"], "claimedBySessionUuid": None,
        "claimAttemptedAt": None, "executionCount": 0, "createdAt": "z",
        "awaitingLaunchAt": "z", "startedAt": None, "completedAt": None,
        "result": None, "errors": [],
    })
    (v2_project / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    res = validate_prerequisites(v2_project, "ptk-orphan")
    assert res["ok"] is False
    assert "missing" in res["blockMessage"]


# ---- freeze_splits ----


def _write_phase_config(project_root: Path, phase: str, payload: dict) -> None:
    (project_root / f"shipwright_{phase}_config.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )


def test_freeze_splits_uses_design_when_present(v2_project):
    _write_phase_config(v2_project, "design", {"splits": ["01-core", "02-ui"]})
    res = freeze_splits(v2_project)
    assert res["ok"] is True
    cfg = _read_cfg(v2_project)
    assert cfg["splits_frozen"] == ["01-core", "02-ui"]
    assert cfg["runConditions"]["splitMode"] == "per_split"


def test_freeze_splits_design_empty_list_sets_none(v2_project):
    _write_phase_config(v2_project, "design", {"splits": []})
    res = freeze_splits(v2_project)
    assert res["ok"] is True
    cfg = _read_cfg(v2_project)
    assert cfg["splits_frozen"] == []
    assert cfg["runConditions"]["splitMode"] == "none"


def test_freeze_splits_falls_back_to_project_when_design_missing(v2_project):
    _write_phase_config(v2_project, "project", {"splits": ["only-one"]})
    res = freeze_splits(v2_project)
    assert res["ok"] is True
    cfg = _read_cfg(v2_project)
    assert cfg["splits_frozen"] == ["only-one"]
    assert cfg["runConditions"]["splitMode"] == "per_split"


def test_freeze_splits_both_missing_records_warning(v2_project):
    res = freeze_splits(v2_project)
    assert res["ok"] is True
    assert res.get("warning") is not None
    cfg = _read_cfg(v2_project)
    assert cfg["splits_frozen"] == []
    assert cfg["runConditions"]["splitMode"] == "none"


def test_freeze_splits_dict_shape_normalised(v2_project):
    _write_phase_config(v2_project, "design", {
        "splits": [{"name": "01-core"}, {"id": "02-ui"}],
    })
    freeze_splits(v2_project)
    cfg = _read_cfg(v2_project)
    assert cfg["splits_frozen"] == ["01-core", "02-ui"]


def test_freeze_splits_design_corrupt_falls_back(v2_project):
    (v2_project / "shipwright_design_config.json").write_text("{not json", encoding="utf-8")
    _write_phase_config(v2_project, "project", {"splits": ["from-project"]})
    freeze_splits(v2_project)
    assert _read_cfg(v2_project)["splits_frozen"] == ["from-project"]


# ---- plan_next_phase ----


def test_plan_next_phase_happy(v2_project):
    tid = _project_task_id(v2_project)
    sid, ver = _claim(v2_project, tid, "project")
    complete_phase_task(v2_project, phase_task_id=tid, session_uuid=sid,
                        expected_version=ver, result={"ok": True})
    # complete_phase_task already planned design; plan_next_phase invoked
    # standalone for the same predecessor must be idempotent.
    res = plan_next_phase(v2_project, completed_phase_task_id=tid)
    assert res["ok"] is True
    cfg = _read_cfg(v2_project)
    designs = [t for t in cfg["phase_tasks"] if t["phase"] == "design"]
    assert len(designs) == 1


def test_plan_next_phase_terminal_returns_pipeline_terminal(v2_project):
    freeze_splits(v2_project)
    last_completed = None
    for phase in ["project", "design", "plan", "build", "test", "changelog", "deploy"]:
        cur = next(t for t in _read_cfg(v2_project)["phase_tasks"]
                   if t["phase"] == phase and t["status"] == "awaiting_launch")
        sid, ver = _claim(v2_project, cur["phaseTaskId"], phase)
        complete_phase_task(v2_project, phase_task_id=cur["phaseTaskId"],
                            session_uuid=sid, expected_version=ver,
                            result={"ok": True})
        last_completed = cur["phaseTaskId"]

    res = plan_next_phase(v2_project, completed_phase_task_id=last_completed)
    assert res["ok"] is True
    assert res["phase_task"]["pipeline_terminal"] is True


def test_plan_next_phase_predecessor_not_found(v2_project):
    res = plan_next_phase(v2_project, completed_phase_task_id="ptk-bogus")
    assert res["ok"] is False
    assert res["reason"] == "not_found"


# ---- find_phase_task_by_session_uuid ----


def test_find_phase_task_by_session_uuid(v2_project):
    tid = _project_task_id(v2_project)
    sid = _session_uuid(v2_project, tid)
    found = find_phase_task_by_session_uuid(v2_project, sid)
    assert found is not None and found["phaseTaskId"] == tid

    assert find_phase_task_by_session_uuid(v2_project, "nope") is None


# ---- get_phase_task ----


def test_get_phase_task(v2_project):
    tid = _project_task_id(v2_project)
    res = get_phase_task(v2_project, tid)
    assert res["ok"] is True
    assert res["phase_task"]["phaseTaskId"] == tid


def test_get_phase_task_not_found(v2_project):
    res = get_phase_task(v2_project, "ptk-nope")
    assert res["ok"] is False
    assert res["reason"] == "not_found"

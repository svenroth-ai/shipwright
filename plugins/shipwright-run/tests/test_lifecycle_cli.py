"""CLI smoke tests for F2 phase-task lifecycle subcommands.

Validates argparse wiring + exit-code semantics. Behaviour is covered
exhaustively by test_phase_task_lifecycle.py — these tests just confirm
the CLI surface works end-to-end with subprocess invocations.

Exit code map (Plan v4 §F2):
    0 = ok
    1 = generic error (not_found, invalid args, missing result JSON)
    2 = fail-closed (wrong_skill, duplicate_claim, stale_*, prereqs_unmet, ...)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config  # noqa: E402

ORCHESTRATOR = str(
    Path(__file__).resolve().parent.parent / "scripts" / "lib" / "orchestrator.py",
)


def _run(args: list[str], project_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, ORCHESTRATOR, *args, "--project-root", str(project_root)],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )


def _setup_project(project_root: Path, monkeypatch) -> dict:
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    create_config(
        scope="full_app", profile="supabase-nextjs",
        autonomy="guided", deploy_target="jelastic-dev",
        project_root=project_root,
    )
    return json.loads((project_root / "shipwright_run_config.json").read_text("utf-8"))


def test_get_phase_task_cli_ok(tmp_project, monkeypatch):
    cfg = _setup_project(tmp_project, monkeypatch)
    tid = cfg["phase_tasks"][0]["phaseTaskId"]
    res = _run(["get-phase-task", "--phase-task-id", tid], tmp_project)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["ok"] is True
    assert out["phase_task"]["phaseTaskId"] == tid


def test_get_phase_task_cli_not_found_exits_1(tmp_project, monkeypatch):
    _setup_project(tmp_project, monkeypatch)
    res = _run(["get-phase-task", "--phase-task-id", "ptk-nope"], tmp_project)
    assert res.returncode == 1
    assert json.loads(res.stdout)["reason"] == "not_found"


def test_find_phase_task_by_session_uuid_cli(tmp_project, monkeypatch):
    cfg = _setup_project(tmp_project, monkeypatch)
    sid = cfg["phase_tasks"][0]["sessionUuid"]
    res = _run(["find-phase-task-by-session-uuid", "--session-uuid", sid], tmp_project)
    assert res.returncode == 0
    out = json.loads(res.stdout)
    assert out["ok"] is True
    assert out["phase_task"]["sessionUuid"] == sid


def test_claim_wrong_skill_exits_2_fail_closed(tmp_project, monkeypatch):
    cfg = _setup_project(tmp_project, monkeypatch)
    tid = cfg["phase_tasks"][0]["phaseTaskId"]
    sid = cfg["phase_tasks"][0]["sessionUuid"]
    res = _run([
        "claim-phase-task",
        "--phase-task-id", tid,
        "--session-uuid", sid,
        "--expected-phase", "build",  # Wrong! task.phase is "project"
    ], tmp_project)
    assert res.returncode == 2, f"expected fail-closed exit 2, got {res.returncode}: {res.stdout}"
    out = json.loads(res.stdout)
    assert out["ok"] is False
    assert out["reason"] == "wrong_skill"


def test_claim_happy_then_complete_via_cli(tmp_project, monkeypatch):
    cfg = _setup_project(tmp_project, monkeypatch)
    tid = cfg["phase_tasks"][0]["phaseTaskId"]
    sid = cfg["phase_tasks"][0]["sessionUuid"]

    # claim
    res = _run([
        "claim-phase-task", "--phase-task-id", tid,
        "--session-uuid", sid, "--expected-phase", "project",
    ], tmp_project)
    assert res.returncode == 0, res.stdout
    claimed_version = json.loads(res.stdout)["phase_task"]["version"]

    # complete
    result_file = tmp_project / "result.json"
    result_file.write_text(json.dumps({"ok": True, "artifacts": []}), encoding="utf-8")
    res = _run([
        "complete-phase-task", "--phase-task-id", tid,
        "--session-uuid", sid, "--version", str(claimed_version),
        "--result-json", str(result_file),
    ], tmp_project)
    assert res.returncode == 0, res.stdout
    out = json.loads(res.stdout)
    assert out["ok"] is True
    assert out["next_phase_task"]["phase"] == "design"


def test_complete_missing_result_json_exits_1(tmp_project, monkeypatch):
    cfg = _setup_project(tmp_project, monkeypatch)
    tid = cfg["phase_tasks"][0]["phaseTaskId"]
    sid = cfg["phase_tasks"][0]["sessionUuid"]
    res = _run([
        "complete-phase-task", "--phase-task-id", tid,
        "--session-uuid", sid, "--version", "1",
        "--result-json", str(tmp_project / "nope.json"),
    ], tmp_project)
    assert res.returncode == 1


def test_freeze_splits_cli(tmp_project, monkeypatch):
    _setup_project(tmp_project, monkeypatch)
    (tmp_project / "shipwright_design_config.json").write_text(
        json.dumps({"splits": ["a", "b"]}), encoding="utf-8",
    )
    res = _run(["freeze-splits"], tmp_project)
    assert res.returncode == 0
    cfg = json.loads((tmp_project / "shipwright_run_config.json").read_text("utf-8"))
    assert cfg["splits_frozen"] == ["a", "b"]
    assert cfg["runConditions"]["splitMode"] == "per_split"


def test_recover_phase_task_cli(tmp_project, monkeypatch):
    cfg = _setup_project(tmp_project, monkeypatch)
    tid = cfg["phase_tasks"][0]["phaseTaskId"]
    sid = cfg["phase_tasks"][0]["sessionUuid"]
    _run([
        "claim-phase-task", "--phase-task-id", tid,
        "--session-uuid", sid, "--expected-phase", "project",
    ], tmp_project)
    res = _run([
        "recover-phase-task", "--phase-task-id", tid,
    ], tmp_project)
    assert res.returncode == 0
    out = json.loads(res.stdout)
    assert out["new_version"] == 2
    assert out["phase_task"]["claimedBySessionUuid"] is None


def test_validate_prerequisites_unmet_exits_2(tmp_project, monkeypatch):
    cfg = _setup_project(tmp_project, monkeypatch)
    # Inject a fake design task whose prereq (project) is still awaiting_launch
    pj = cfg["phase_tasks"][0]
    cfg["phase_tasks"].append({
        "phaseTaskId": "ptk-design-fake", "phase": "design", "splitId": None,
        "sessionUuid": "x", "version": 1, "status": "awaiting_launch",
        "title": "design", "slashCommand": "/shipwright-design",
        "prerequisites": [pj["phaseTaskId"]],
        "claimedBySessionUuid": None, "claimAttemptedAt": None,
        "executionCount": 0, "createdAt": "z", "awaitingLaunchAt": "z",
        "startedAt": None, "completedAt": None, "result": None, "errors": [],
    })
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8",
    )
    res = _run([
        "validate-prerequisites", "--phase-task-id", "ptk-design-fake",
    ], tmp_project)
    assert res.returncode == 2
    out = json.loads(res.stdout)
    assert out["reason"] == "prereqs_unmet"


def test_plan_next_phase_cli(tmp_project, monkeypatch):
    cfg = _setup_project(tmp_project, monkeypatch)
    pj = cfg["phase_tasks"][0]
    # Force project to done so plan_next_phase can compute design
    pj["status"] = "done"
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8",
    )
    res = _run([
        "plan-next-phase", "--phase-task-id", pj["phaseTaskId"],
    ], tmp_project)
    assert res.returncode == 0
    out = json.loads(res.stdout)
    assert out["ok"] is True
    assert out["phase_task"]["phase"] == "design"

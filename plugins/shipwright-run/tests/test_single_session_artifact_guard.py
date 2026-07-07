"""On-disk PERSISTENCE GUARD for single-session apply (Campaign 2026-07-07, SS4).

The SS4 loop-level enforcement of the phase-runner artifact contract: an
``ok`` result may not CLAIM an artifact it did not write to disk. This closes
the section-writer silent-loss class at ``apply_phase_result`` — a claimed but
unwritten artifact is rejected fail-closed BEFORE any lifecycle mutation, while
an ``ok=False`` strict-stop is never blocked by a (legitimately) absent artifact.

Kept in its own module (not ``test_single_session_loop.py``) so both files stay
under the 300-line source/test ceiling.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle  # noqa: E402
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from single_session.result_contract import build_phase_runner_result  # noqa: E402


def _ss_config(project_root: Path):
    return create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev",
        project_root, mode="single_session",
    )


def _result(phase: str, *, ok: bool = True):
    return build_phase_runner_result(
        ok=ok,
        phase=phase,
        summary=f"{phase} done" if ok else f"{phase} failed",
        artifacts=[f"artifacts/{phase}.md"],
        reason=None if ok else f"{phase} blew up",
    )


def _dispatch_seed(project_root: Path):
    nxt = loop.next_dispatch(project_root)
    assert nxt["action"] == "dispatch", nxt
    return nxt["dispatch"]


def test_apply_rejects_missing_artifact_before_lifecycle(tmp_project):
    config = _ss_config(tmp_project)
    seed_id = config["phase_tasks"][0]["phaseTaskId"]
    dispatch = _dispatch_seed(tmp_project)

    # ok result CLAIMS artifacts/project.md — but the phase-runner never wrote it.
    applied = loop.apply_phase_result(
        tmp_project,
        phase_task_id=dispatch["phaseTaskId"],
        session_uuid=dispatch["sessionUuid"],
        expected_version=dispatch["version"],
        result=_result("project"),  # artifacts/project.md NOT on disk
    )
    assert applied["ok"] is False
    assert applied["reason"] == "artifacts_missing"
    assert applied["missing"] == ["artifacts/project.md"]

    # Guard fired before any lifecycle MUTATION — task still in_progress, run untouched.
    task = phase_task_lifecycle.get_phase_task(tmp_project, seed_id)["phase_task"]
    assert task["status"] == "in_progress"
    cfg = json.loads((tmp_project / "shipwright_run_config.json").read_text("utf-8"))
    assert cfg["status"] == "in_progress"


def test_apply_accepts_when_claimed_artifact_on_disk(tmp_project):
    _ss_config(tmp_project)
    dispatch = _dispatch_seed(tmp_project)

    # Phase-runner persisted its artifact to disk before returning — guard passes.
    art = tmp_project / "artifacts" / "project.md"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text("# project\n", encoding="utf-8")

    applied = loop.apply_phase_result(
        tmp_project,
        phase_task_id=dispatch["phaseTaskId"],
        session_uuid=dispatch["sessionUuid"],
        expected_version=dispatch["version"],
        result=_result("project"),
    )
    assert applied["ok"] is True
    assert applied["next"]["action"] == "dispatch"


def test_apply_stale_version_reports_stale_not_artifacts_missing(tmp_project):
    # A stale re-apply whose artifact is also missing must surface the truthful
    # CAS reason (stale_version), NOT be pre-empted by the artifact guard.
    config = _ss_config(tmp_project)
    seed_id = config["phase_tasks"][0]["phaseTaskId"]
    dispatch = _dispatch_seed(tmp_project)
    phase_task_lifecycle.recover_phase_task(tmp_project, phase_task_id=seed_id)  # bump version

    applied = loop.apply_phase_result(
        tmp_project,
        phase_task_id=dispatch["phaseTaskId"],
        session_uuid=dispatch["sessionUuid"],
        expected_version=dispatch["version"],  # now stale
        result=_result("project"),  # artifacts/project.md deliberately NOT on disk
    )
    assert applied["ok"] is False
    assert applied["reason"] == "stale_version"


def test_apply_failure_result_skips_artifact_guard(tmp_project):
    # An ok=False result need not have written artifacts; the guard must not
    # block a legitimate strict-stop just because the artifact is missing.
    _ss_config(tmp_project)
    dispatch = _dispatch_seed(tmp_project)
    applied = loop.apply_phase_result(
        tmp_project,
        phase_task_id=dispatch["phaseTaskId"],
        session_uuid=dispatch["sessionUuid"],
        expected_version=dispatch["version"],
        result=_result("project", ok=False),  # no artifact on disk — must be fine
    )
    assert applied["ok"] is True  # completion succeeded; failure is data
    assert applied["run_status"] == "failed"

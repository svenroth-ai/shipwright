"""Dual-mode BACK-COMPAT suite (SS5, AC2).

The whole point of SS5's isolation: a ``multi_session`` run stays on the OLD path,
completely untouched by the single-session resumability/observability machinery. These
tests are the machine-checkable statement of that guarantee:

  * driving a ``multi_session`` run through the lifecycle (claim -> complete, and
    recover) creates NEITHER ``run_loop_state.json`` NOR ``run_loop_events.jsonl``;
  * every new SS5 entry point (resume / gate / recover) refuses a ``multi_session`` run
    with ``wrong_mode`` and writes NO file — the belt-and-suspenders the external review
    asked for (don't rely on "we don't call these paths");
  * a pre-SS5 single_session run (loop_state present, no events file yet) resumes cleanly
    — back-compat includes older single_session runs, not just multi_session.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle as lc  # noqa: E402
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from orchestrator_pkg import single_session_recovery as rec  # noqa: E402
from single_session import observability as obs  # noqa: E402
from single_session.loop_state import (  # noqa: E402
    init_loop_state,
    loop_state_path,
    save_loop_state,
)


def _multi_config(project_root: Path):
    return create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev", project_root,
    )


def _frontier(config: dict) -> dict:
    for t in config.get("phase_tasks", []):
        if t.get("status") in ("awaiting_launch", "in_progress"):
            return t
    raise AssertionError("no dispatchable task in config")


def _no_single_session_files(project_root: Path) -> bool:
    return (
        not loop_state_path(project_root).exists()
        and not obs.events_path(project_root).exists()
    )


# --------------------------------------------------------------------------- #
# The multi_session lifecycle leaves no single-session artefacts
# --------------------------------------------------------------------------- #

def test_multi_session_claim_complete_creates_no_single_session_files(tmp_project):
    cfg = _multi_config(tmp_project)
    assert cfg["mode"] == "multi_session"
    task = _frontier(cfg)

    claim = lc.claim_phase_task(
        tmp_project, phase_task_id=task["phaseTaskId"],
        session_uuid=task["sessionUuid"], expected_phase="project",
    )
    assert claim["ok"], claim
    claimed = claim["phase_task"]

    comp = lc.complete_phase_task(
        tmp_project, phase_task_id=claimed["phaseTaskId"],
        session_uuid=claimed["sessionUuid"], expected_version=claimed["version"],
        result={"ok": True, "phase": "project", "summary": "done", "artifacts": []},
    )
    assert comp["ok"], comp
    # The multi_session path never touches single-session state/telemetry.
    assert _no_single_session_files(tmp_project)


def test_multi_session_recover_via_lifecycle_creates_no_single_session_files(tmp_project):
    cfg = _multi_config(tmp_project)
    task = _frontier(cfg)
    # The GENERIC recover-phase-task (what multi_session uses) is untouched by SS5.
    out = lc.recover_phase_task(tmp_project, phase_task_id=task["phaseTaskId"])
    assert out["ok"], out
    assert _no_single_session_files(tmp_project)


def test_resolve_next_dispatch_is_wrong_mode_for_multi_session(tmp_project):
    _multi_config(tmp_project)
    assert loop.resolve_next_dispatch(tmp_project)["action"] == "wrong_mode"


# --------------------------------------------------------------------------- #
# Every SS5 entry point refuses multi_session with no file creation
# --------------------------------------------------------------------------- #

def test_resume_refuses_multi_session_no_files(tmp_project):
    _multi_config(tmp_project)
    assert rec.resume_run(tmp_project)["action"] == "wrong_mode"
    assert rec.resume_run(tmp_project, confirm=True)["action"] == "wrong_mode"
    assert _no_single_session_files(tmp_project)


def test_gate_refuses_multi_session_no_files(tmp_project):
    _multi_config(tmp_project)
    res = rec.mark_human_gate(tmp_project, phase_task_id="ptk", phase="plan", paused=True)
    assert res["ok"] is False and res["action"] == "wrong_mode"
    assert _no_single_session_files(tmp_project)


def test_recover_refuses_multi_session_no_files(tmp_project):
    _multi_config(tmp_project)
    res = rec.recover_single_session(tmp_project, phase_task_id="ptk")
    assert res["ok"] is False and res["action"] == "wrong_mode"
    assert _no_single_session_files(tmp_project)


# --------------------------------------------------------------------------- #
# Pre-SS5 single_session runs (no events file yet) resume cleanly
# --------------------------------------------------------------------------- #

def test_pre_ss5_single_session_loop_state_resumes_without_events_file(tmp_project):
    cfg = create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev",
        tmp_project, mode="single_session",
    )
    # An SS3/SS4-era run: loop_state persisted, but no run_loop_events.jsonl exists.
    save_loop_state(tmp_project, init_loop_state(cfg["runId"]))
    assert not obs.events_path(tmp_project).exists()

    res = rec.resume_run(tmp_project)  # read-only detection must not choke
    assert res["action"] == "resume"
    assert res["resumeAction"] == "dispatch"
    # Still no events file — read-only detection emits nothing.
    assert not obs.events_path(tmp_project).exists()

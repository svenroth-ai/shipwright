"""Tests for single-session RESUME + RECOVERY + human-gate observability (SS5).

Campaign 2026-07-07-single-session-pipeline / SS5. Covers
``orchestrator_pkg.single_session_recovery``: the read-only resume decision (confirm
card), the human-gate pause/resume, and the in-loop recover-phase-task escape — each
mode- and run-identity-gated, each emitting observability only on the single-session path.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import single_session_recovery as rec  # noqa: E402
from single_session import observability as obs  # noqa: E402
from single_session.loop_state import (  # noqa: E402
    init_loop_state,
    load_loop_state,
    save_loop_state,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _ss_config(project_root: Path):
    return create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev",
        project_root, mode="single_session",
    )


def _multi_config(project_root: Path):
    # SS8: single_session is the default now — request multi_session explicitly.
    return create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev", project_root,
        mode="multi_session",
    )


def _seed(project_root: Path, *, run_id: str | None = None) -> str:
    """Single_session config + a matching loop_state. Returns the run_id."""
    cfg = _ss_config(project_root)
    rid = run_id or cfg["runId"]
    save_loop_state(project_root, init_loop_state(rid))
    return cfg["runId"]


def _frontier_id(project_root: Path) -> str:
    from orchestrator_pkg import single_session_loop as loop
    return loop.resolve_next_dispatch(project_root)["dispatch"]["phaseTaskId"]


# --------------------------------------------------------------------------- #
# resume_run — guard rejections (no side effects)
# --------------------------------------------------------------------------- #

def test_resume_no_config(tmp_project):
    assert rec.resume_run(tmp_project)["action"] == "no_config"


def test_resume_wrong_mode_on_multi_session(tmp_project):
    _multi_config(tmp_project)
    res = rec.resume_run(tmp_project)
    assert res["action"] == "wrong_mode"
    # A multi_session run must not grow single-session telemetry.
    assert obs.load_events(tmp_project) == []
    assert not obs.events_path(tmp_project).exists()


def test_resume_not_resumable_without_loop_state(tmp_project):
    _ss_config(tmp_project)  # no loop_state seeded
    res = rec.resume_run(tmp_project)
    assert res["action"] == "not_resumable"
    assert res["reason"] == "no_loop_state"


def test_resume_runid_mismatch_refuses_stale_loop_state(tmp_project):
    _seed(tmp_project, run_id="run-STALE99")  # loop_state from a different run
    res = rec.resume_run(tmp_project)
    assert res["action"] == "runid_mismatch"
    assert res["loop_state_run_id"] == "run-STALE99"
    assert res["config_run_id"] != "run-STALE99"


# --------------------------------------------------------------------------- #
# resume_run — read-only detection vs confirmed commitment
# --------------------------------------------------------------------------- #

def test_resume_is_read_only_and_emits_nothing_without_confirm(tmp_project):
    _seed(tmp_project)
    before = load_loop_state(tmp_project)
    res = rec.resume_run(tmp_project)  # confirm defaults False
    assert res["action"] == "resume"
    assert res["resumeAction"] == "dispatch"  # frontier project task
    assert res["confirmed"] is False
    # No event, no loop_state mutation on mere detection.
    assert obs.load_events(tmp_project) == []
    assert load_loop_state(tmp_project)["attempt"] == before["attempt"]


def test_resume_confirm_emits_a_single_resume_event(tmp_project):
    run_id = _seed(tmp_project)
    res = rec.resume_run(tmp_project, confirm=True)
    assert res["action"] == "resume"
    assert res["confirmed"] is True
    events = obs.load_events(tmp_project)
    assert [e["event"] for e in events] == ["resume"]
    assert events[0]["runId"] == run_id
    assert events[0]["resumeAction"] == "dispatch"
    # Whitelisted fields only — no full context/next blob leaked into the event.
    assert "context" not in events[0]
    assert "next" not in events[0]


def test_resume_carries_compact_context_and_next_in_return(tmp_project):
    _seed(tmp_project)
    res = rec.resume_run(tmp_project)
    assert res["context"]["mode"] == "single_session"
    assert res["next"]["action"] == "dispatch"
    assert set(res["loopState"]) == {
        "status", "currentPhaseTaskId", "lastCompletedPhaseTaskId", "attempt",
    }


# --------------------------------------------------------------------------- #
# mark_human_gate
# --------------------------------------------------------------------------- #

def test_human_gate_pause_then_resume_flips_status_and_emits(tmp_project):
    run_id = _seed(tmp_project)
    ptk = _frontier_id(tmp_project)

    paused = rec.mark_human_gate(tmp_project, phase_task_id=ptk, phase="plan", paused=True)
    assert paused["ok"] is True
    assert paused["status"] == "paused_human_gate"
    assert load_loop_state(tmp_project)["status"] == "paused_human_gate"

    resumed = rec.mark_human_gate(tmp_project, phase_task_id=ptk, phase="plan", paused=False)
    assert resumed["status"] == "running"
    assert load_loop_state(tmp_project)["status"] == "running"

    events = obs.load_events(tmp_project)
    assert [e["event"] for e in events] == ["human_gate_pause", "human_gate_resume"]
    assert events[0]["phaseTaskId"] == ptk
    assert all(e["runId"] == run_id for e in events)


def test_human_gate_refused_on_multi_session_no_mutation(tmp_project):
    _multi_config(tmp_project)
    res = rec.mark_human_gate(tmp_project, phase_task_id="ptk-x", phase="plan", paused=True)
    assert res["ok"] is False
    assert res["action"] == "wrong_mode"
    assert load_loop_state(tmp_project) is None  # no loop_state created
    assert obs.load_events(tmp_project) == []


# --------------------------------------------------------------------------- #
# recover_single_session
# --------------------------------------------------------------------------- #

def test_recover_single_session_resets_pointer_and_emits(tmp_project):
    run_id = _seed(tmp_project)
    ptk = _frontier_id(tmp_project)

    res = rec.recover_single_session(tmp_project, phase_task_id=ptk)
    assert res["ok"] is True
    assert res["recover"]["ok"] is True
    ls = load_loop_state(tmp_project)
    assert ls["currentPhaseTaskId"] == ptk
    assert ls["attempt"] == 0

    events = obs.load_events(tmp_project)
    assert [e["event"] for e in events] == ["recovery"]
    assert events[0]["phaseTaskId"] == ptk
    assert events[0]["forceStatus"] == "awaiting_launch"
    assert events[0]["runId"] == run_id


def test_recover_refused_on_runid_mismatch(tmp_project):
    _seed(tmp_project, run_id="run-STALE99")
    res = rec.recover_single_session(tmp_project, phase_task_id="ptk-anything")
    assert res["ok"] is False
    assert res["action"] == "runid_mismatch"
    assert obs.load_events(tmp_project) == []


def test_recover_refused_on_multi_session(tmp_project):
    _multi_config(tmp_project)
    res = rec.recover_single_session(tmp_project, phase_task_id="ptk-x")
    assert res["ok"] is False
    assert res["action"] == "wrong_mode"
    assert not obs.events_path(tmp_project).exists()


# --------------------------------------------------------------------------- #
# Code-review regressions (SS5 review findings #1-#3, #5)
# --------------------------------------------------------------------------- #

def _read_cfg(project_root: Path) -> dict:
    import json
    return json.loads((project_root / "shipwright_run_config.json").read_text("utf-8"))


def _write_cfg(project_root: Path, data: dict) -> None:
    import json
    (project_root / "shipwright_run_config.json").write_text(json.dumps(data), "utf-8")


def test_next_dispatch_reinits_stale_loop_state_from_prior_run(tmp_project):
    """#1: a stale loop-state from a PRIOR run in this dir must NOT be reused — the
    dispatch/loop pointer must belong to the CURRENT run, not the old runId."""
    from orchestrator_pkg import single_session_loop as loop
    cfg = _ss_config(tmp_project)
    save_loop_state(tmp_project, init_loop_state("run-PRIOR99", current_phase_task_id="ptk-old"))

    nxt = loop.next_dispatch(tmp_project)
    assert nxt["action"] == "dispatch"
    assert load_loop_state(tmp_project)["runId"] == cfg["runId"]
    events = obs.load_events(tmp_project)
    assert events and events[-1]["runId"] == cfg["runId"]  # not logged under run-PRIOR99


def test_resume_terminal_run_passes_through_and_emits_nothing(tmp_project):
    """#2: a complete/failed run is NOT resumable — surface the terminal signal and,
    even with --confirm, emit no spurious resume event."""
    cfg = _ss_config(tmp_project)
    save_loop_state(tmp_project, init_loop_state(cfg["runId"]))
    data = _read_cfg(tmp_project)
    data["status"] = "complete"
    _write_cfg(tmp_project, data)

    res = rec.resume_run(tmp_project, confirm=True)
    assert res["action"] == "complete"          # real terminal signal, not "resume"
    assert "confirmed" not in res               # terminal branch never reaches the confirm path
    assert obs.load_events(tmp_project) == []   # no spurious resume event


def test_recover_unrelated_task_does_not_lift_failed_run(tmp_project):
    """#3: recovering an unrelated awaiting_launch task must NOT lift the loop to
    running while the run stays failed (recover_phase_task only lifts config.status
    when THIS task carried the failure)."""
    from single_session.loop_state import set_status
    cfg = _ss_config(tmp_project)
    data = _read_cfg(tmp_project)
    a_id = data["phase_tasks"][0]["phaseTaskId"]  # awaiting_launch project task
    data["phase_tasks"].append({"phaseTaskId": "ptk-failedB", "phase": "plan",
                                "status": "failed", "sessionUuid": "sess-b", "version": 1})
    data["status"] = "failed"
    _write_cfg(tmp_project, data)
    save_loop_state(tmp_project, set_status(init_loop_state(cfg["runId"]), "failed"))

    res = rec.recover_single_session(tmp_project, phase_task_id=a_id)
    assert res["ok"] is True
    assert _read_cfg(tmp_project)["status"] == "failed"   # unrelated recover left it failed
    assert load_loop_state(tmp_project)["status"] == "failed"  # loop must agree, not "running"


def test_double_apply_is_idempotent_and_preserves_pointer(tmp_project):
    """#5: a double-apply of an already-done task must not null the loop pointer or
    emit a spurious runStatus=null phase_result."""
    from orchestrator_pkg import single_session_loop as loop
    from single_session.result_contract import build_phase_runner_result
    _ss_config(tmp_project)
    d = loop.next_dispatch(tmp_project)["dispatch"]
    (tmp_project / "artifacts").mkdir(exist_ok=True)
    (tmp_project / "artifacts" / "project.md").write_text("x", "utf-8")
    result = build_phase_runner_result(
        ok=True, phase="project", summary="done", artifacts=["artifacts/project.md"],
    )
    apply_kwargs = dict(phase_task_id=d["phaseTaskId"], session_uuid=d["sessionUuid"],
                        expected_version=d["version"], result=result)
    assert loop.apply_phase_result(tmp_project, **apply_kwargs)["ok"] is True

    ptr_before = load_loop_state(tmp_project)["currentPhaseTaskId"]
    n_events_before = len(obs.load_events(tmp_project))
    # Apply the SAME (now-done) task again — complete_phase_task returns idempotent.
    assert loop.apply_phase_result(tmp_project, **apply_kwargs)["ok"] is True
    assert load_loop_state(tmp_project)["currentPhaseTaskId"] == ptr_before
    assert len(obs.load_events(tmp_project)) == n_events_before  # no spurious event

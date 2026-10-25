"""A skip that clears the last ``needs_validation`` blocker completes the run.

``complete_phase_task`` parks a run in ``needs_validation`` when the pipeline-terminal
task (deploy, or changelog with ``deploy_target: none``) completes while other tasks are
still open. The documented way out is ``recover-phase-task --force-status skipped`` per
open task; before this fix nothing re-checked the run once they were all terminal, so
``single-session-next`` answered ``needs_validation`` forever and the run never finished.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle as lc  # noqa: E402
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import cli as cli_mod  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from orchestrator_pkg.single_session_recovery import (  # noqa: E402
    mark_loop_complete,
    recover_single_session,
)
from single_session.loop_state import (  # noqa: E402
    init_loop_state,
    load_loop_state,
    save_loop_state,
    set_status,
)
from single_session.observability import load_events  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC01")

CONFIG = "shipwright_run_config.json"
_PIPELINE = ("project", "design", "plan", "build", "test", "changelog", "deploy")


def _cfg(root: Path) -> dict:
    return json.loads((root / CONFIG).read_text(encoding="utf-8"))


def _write(root: Path, cfg: dict) -> None:
    (root / CONFIG).write_text(json.dumps(cfg), encoding="utf-8")


def _orphan(ptk: str) -> dict:
    return {
        "phaseTaskId": ptk, "phase": "test", "splitId": None, "sessionUuid": f"{ptk}-uuid",
        "version": 1, "status": "in_progress", "title": "orphan",
        "slashCommand": "/shipwright-test", "prerequisites": [],
        "claimedBySessionUuid": "x", "claimAttemptedAt": None, "executionCount": 1,
        "createdAt": "z", "awaitingLaunchAt": None, "startedAt": "z", "completedAt": None,
        "result": None, "errors": [],
    }


def _complete(root: Path, phase: str) -> dict:
    cur = next(t for t in _cfg(root)["phase_tasks"]
               if t["phase"] == phase and t["status"] == "awaiting_launch")
    claim = lc.claim_phase_task(root, phase_task_id=cur["phaseTaskId"],
                                session_uuid=cur["sessionUuid"], expected_phase=phase)
    assert claim["ok"], claim
    res = lc.complete_phase_task(root, phase_task_id=cur["phaseTaskId"],
                                 session_uuid=cur["sessionUuid"],
                                 expected_version=claim["phase_task"]["version"],
                                 result={"ok": True})
    assert res["ok"], res
    return res


def _blocked_run(root: Path, *, orphans: int = 1, deploy_target: str = "jelastic-dev",
                 loop_state: bool = True) -> list[str]:
    """Walk the real lifecycle to the pipeline-terminal phase with ``orphans`` open tasks,
    so its completion parks the run in ``needs_validation``. Returns the orphan ids."""
    create_config("full_app", "supabase-nextjs", "guided", deploy_target, root,
                  mode="single_session")
    lc.freeze_splits(root)
    phases = _PIPELINE if deploy_target != "none" else _PIPELINE[:-1]
    for phase in phases[:-1]:
        _complete(root, phase)
    ids = [f"ptk-orphan-{i}" for i in range(orphans)]
    cfg = _cfg(root)
    cfg["phase_tasks"].extend(_orphan(i) for i in ids)
    _write(root, cfg)
    last = _complete(root, phases[-1])
    assert last["run_status"] == "needs_validation", last
    if loop_state:  # what single-session-apply's _advance_loop_state leaves after it
        state = init_loop_state(_cfg(root)["runId"], current_phase_task_id=None)
        save_loop_state(root, set_status(state, "stopped"))
    return ids


def _skip(root: Path, ptk: str) -> dict:
    res = lc.recover_phase_task(root, phase_task_id=ptk, force_status="skipped",
                                reason="not needed for this release")
    assert res["ok"], res
    return res


def test_skipping_the_last_open_task_completes_the_run_in_the_same_write(tmp_project):
    (ptk,) = _blocked_run(tmp_project)
    res = _skip(tmp_project, ptk)
    assert res["run_status"] == "complete"
    cfg = _cfg(tmp_project)
    assert cfg["status"] == "complete"
    task = next(t for t in cfg["phase_tasks"] if t["phaseTaskId"] == ptk)
    assert task["status"] == "skipped"          # never rewritten to done
    assert loop.resolve_next_dispatch(tmp_project) == {"action": "complete"}


def test_a_skip_that_leaves_another_task_open_keeps_needs_validation(tmp_project):
    first, second = _blocked_run(tmp_project, orphans=2)
    res = _skip(tmp_project, first)
    assert "run_status" not in res
    assert _cfg(tmp_project)["status"] == "needs_validation"
    nxt = loop.resolve_next_dispatch(tmp_project)
    assert nxt["action"] == "needs_validation"
    assert [b["phaseTaskId"] for b in nxt["blocked"]] == [second]

    assert _skip(tmp_project, second)["run_status"] == "complete"
    assert _cfg(tmp_project)["status"] == "complete"


def test_validation_issues_from_the_v1_producer_are_not_lifted(tmp_project):
    (ptk,) = _blocked_run(tmp_project)
    cfg = _cfg(tmp_project)
    cfg["validation_issues"] = [{"step": "test", "level": "ask", "message": "no results"}]
    _write(tmp_project, cfg)
    res = _skip(tmp_project, ptk)
    assert "run_status" not in res
    cfg = _cfg(tmp_project)
    assert cfg["status"] == "needs_validation" and cfg["validation_issues"]


def test_no_completion_while_the_pipeline_terminal_task_is_not_done(tmp_project):
    (ptk,) = _blocked_run(tmp_project)
    cfg = _cfg(tmp_project)
    deploy = next(t for t in cfg["phase_tasks"] if t["phase"] == "deploy")
    deploy["status"] = "skipped"                 # terminal, but deploy did not happen
    _write(tmp_project, cfg)
    res = _skip(tmp_project, ptk)
    assert "run_status" not in res
    assert _cfg(tmp_project)["status"] == "needs_validation"


def test_a_run_without_deploy_completes_on_changelog(tmp_project):
    (ptk,) = _blocked_run(tmp_project, deploy_target="none")
    assert not any(t["phase"] == "deploy" for t in _cfg(tmp_project)["phase_tasks"])
    assert _skip(tmp_project, ptk)["run_status"] == "complete"
    assert _cfg(tmp_project)["status"] == "complete"


def test_recovering_the_last_open_task_as_failed_does_not_complete_the_run(tmp_project):
    (ptk,) = _blocked_run(tmp_project)
    res = lc.recover_phase_task(tmp_project, phase_task_id=ptk, force_status="failed")
    assert res["ok"] and "run_status" not in res
    assert _cfg(tmp_project)["status"] == "needs_validation"


def test_skipping_again_is_idempotent(tmp_project):
    (ptk,) = _blocked_run(tmp_project)
    _skip(tmp_project, ptk)
    again = _skip(tmp_project, ptk)
    assert "run_status" not in again             # nothing left to lift
    cfg = _cfg(tmp_project)
    assert cfg["status"] == "complete"
    assert cfg["completed_phase_task_ids"].count(ptk) == 1


def test_a_skip_on_a_running_run_does_not_complete_it(tmp_project):
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project,
                  mode="single_session")
    ptk = _cfg(tmp_project)["phase_tasks"][0]["phaseTaskId"]
    res = _skip(tmp_project, ptk)                # every task terminal, but no deploy yet
    assert "run_status" not in res
    assert _cfg(tmp_project)["status"] == "in_progress"


def _cli(monkeypatch, capsys, *argv: str) -> tuple[int, dict]:
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", *argv])
    rc = cli_mod.main()
    return rc, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("command", ["recover-phase-task", "single-session-recover"])
def test_both_recover_clis_report_completion_and_stamp_the_loop(
        tmp_project, monkeypatch, capsys, command):
    (ptk,) = _blocked_run(tmp_project)
    assert load_loop_state(tmp_project)["status"] == "stopped"   # what the deploy apply left
    rc, out = _cli(monkeypatch, capsys, command, "--project-root", str(tmp_project),
                   "--phase-task-id", ptk, "--force-status", "skipped",
                   "--reason", "not needed for this release")
    assert rc == 0, out
    recovered = out if command == "recover-phase-task" else out["recover"]
    assert recovered["run_status"] == "complete"
    if command == "single-session-recover":
        assert out["loopState"]["status"] == "complete"
        recovery = [e for e in load_events(tmp_project) if e["event"] == "recovery"]
        assert [e["runStatus"] for e in recovery] == ["complete"]
    assert load_loop_state(tmp_project)["status"] == "complete"

    rc, nxt = _cli(monkeypatch, capsys, "single-session-next", "--project-root",
                   str(tmp_project))
    assert (rc, nxt) == (0, {"action": "complete"})


def test_loop_stamp_needs_a_complete_run_of_the_same_run_id(tmp_project):
    (ptk,) = _blocked_run(tmp_project)
    assert mark_loop_complete(tmp_project) is None          # run not complete yet
    assert load_loop_state(tmp_project)["status"] == "stopped"

    _skip(tmp_project, ptk)
    state = load_loop_state(tmp_project)
    save_loop_state(tmp_project, {**state, "runId": "some-other-run"})
    assert mark_loop_complete(tmp_project) is None          # another run's pointer
    assert load_loop_state(tmp_project)["status"] == "stopped"

    save_loop_state(tmp_project, state)
    assert mark_loop_complete(tmp_project)["status"] == "complete"
    assert mark_loop_complete(tmp_project)["status"] == "complete"   # idempotent


def test_no_loop_state_is_left_alone(tmp_project):
    (ptk,) = _blocked_run(tmp_project, loop_state=False)
    _skip(tmp_project, ptk)
    assert mark_loop_complete(tmp_project) is None
    assert load_loop_state(tmp_project) is None


def test_in_loop_recover_on_a_still_blocked_run_leaves_the_loop_stopped(tmp_project):
    first, _second = _blocked_run(tmp_project, orphans=2)
    out = recover_single_session(tmp_project, phase_task_id=first, force_status="skipped",
                                 reason="not needed")
    assert out["ok"] and "run_status" not in out["recover"]
    assert out["loopState"]["status"] == "stopped"
    recovery = [e for e in load_events(tmp_project) if e["event"] == "recovery"]
    assert [e["runStatus"] for e in recovery] == [None]


def test_an_earlier_failed_task_counts_as_terminal_like_the_deploy_completion(tmp_project):
    """Mirrors complete_phase_task: ``failed`` is in TERMINAL_STATUSES, so once the last
    open task is skipped the run completes even though another was recovered ``failed``."""
    failed, last = _blocked_run(tmp_project, orphans=2)
    res = lc.recover_phase_task(tmp_project, phase_task_id=failed, force_status="failed")
    assert res["ok"] and "run_status" not in res
    assert _cfg(tmp_project)["status"] == "needs_validation"
    assert _skip(tmp_project, last)["run_status"] == "complete"
    tasks = {t["phaseTaskId"]: t["status"] for t in _cfg(tmp_project)["phase_tasks"]}
    assert (tasks[failed], tasks[last]) == ("failed", "skipped")


@pytest.mark.parametrize("command", ["recover-phase-task", "single-session-recover"])
def test_a_later_skip_repairs_a_loop_write_lost_after_completion(
        tmp_project, monkeypatch, capsys, command):
    (ptk,) = _blocked_run(tmp_project)
    _skip(tmp_project, ptk)                        # run complete, loop write "lost"
    assert load_loop_state(tmp_project)["status"] == "stopped"
    rc, out = _cli(monkeypatch, capsys, command, "--project-root", str(tmp_project),
                   "--phase-task-id", ptk, "--force-status", "skipped", "--reason", "again")
    assert rc == 0, out
    assert load_loop_state(tmp_project)["status"] == "complete"


def test_loop_stamp_refuses_a_config_that_is_not_a_single_session_run(tmp_project):
    (ptk,) = _blocked_run(tmp_project)
    _skip(tmp_project, ptk)
    cfg = _cfg(tmp_project)
    cfg.pop("mode")
    _write(tmp_project, cfg)
    assert mark_loop_complete(tmp_project) is None
    assert load_loop_state(tmp_project)["status"] == "stopped"

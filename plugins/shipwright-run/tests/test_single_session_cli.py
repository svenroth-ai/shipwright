"""Unit tests for the single-session CLI adapter (Campaign 2026-07-07, SS3).

These drive ``dispatch_single_session`` and ``cli.main`` IN-PROCESS (not via a
subprocess like the integration test) so the argparse-adapter exit-code map is
covered by the diff-coverage gate: the subprocess path in
``integration-tests/test_single_session_pipeline.py`` proves end-to-end
composition but runs in a child process coverage can't instrument.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle  # noqa: E402
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import cli as cli_mod  # noqa: E402
from orchestrator_pkg.single_session_cli import dispatch_single_session  # noqa: E402
from single_session.loop_state import init_loop_state, save_loop_state  # noqa: E402


def _ss_config(project_root: Path, *, mode: str = "single_session"):
    return create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev", project_root, mode=mode,
    )


def _stale_config(project_root: Path, *, mode: str | None = "multi_session"):
    """Write a NON-DRIVABLE config straight to disk.

    ``create_config`` now refuses the removed mode, so a stale run can only be
    produced the way a real one would be found: already sitting on disk.
    """
    cfg = _ss_config(project_root)
    path = project_root / "shipwright_run_config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if mode is None:
        data.pop("mode", None)
    else:
        data["mode"] = mode
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return cfg


def _ss_config_with_loop_state(project_root: Path):
    """single_session config + a matching loop_state (a resumable run). Returns cfg."""
    cfg = _ss_config(project_root)
    save_loop_state(project_root, init_loop_state(cfg["runId"]))
    return cfg


def _ns(**kw) -> argparse.Namespace:
    return argparse.Namespace(**kw)


def _valid_result(project_root: Path, phase: str = "project", *, ok: bool = True) -> Path:
    artifact_rel = f"artifacts/{phase}.md"
    if ok:  # a successful phase-runner has persisted its artifact to disk (SS4 guard)
        art = project_root / artifact_rel
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text(f"# {phase}\n", encoding="utf-8")
    payload = {"ok": ok, "phase": phase, "summary": f"{phase} done",
               "artifacts": [artifact_rel]}
    if not ok:
        payload["reason"] = f"{phase} failed"
    p = project_root / "result.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# --- single-session-next ---------------------------------------------------

def test_next_exit0_on_dispatch(tmp_project, capsys):
    _ss_config(tmp_project)
    rc = dispatch_single_session(_ns(command="single-session-next"), tmp_project)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["action"] == "dispatch"


def test_next_exit1_on_non_drivable_mode(tmp_project, capsys):
    _stale_config(tmp_project)
    rc = dispatch_single_session(_ns(command="single-session-next"), tmp_project)
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["action"] == "mode_unsupported"


# --- single-session-apply --------------------------------------------------

def _claim_seed(tmp_project):
    """Drive `next` once so the seed project task is claimed; return its ids."""
    cfg = _ss_config(tmp_project)
    seed = cfg["phase_tasks"][0]
    dispatch_single_session(_ns(command="single-session-next"), tmp_project)
    return seed["phaseTaskId"], seed["sessionUuid"]


def test_apply_exit0_on_success(tmp_project, capsys):
    ptk, uuid = _claim_seed(tmp_project)
    capsys.readouterr()
    rc = dispatch_single_session(_ns(
        command="single-session-apply", phase_task_id=ptk, session_uuid=uuid,
        version=1, result_json=str(_valid_result(tmp_project)),
    ), tmp_project)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_apply_exit2_on_stale_cas(tmp_project, capsys):
    ptk, uuid = _claim_seed(tmp_project)
    phase_task_lifecycle.recover_phase_task(tmp_project, phase_task_id=ptk)  # bump version
    capsys.readouterr()
    rc = dispatch_single_session(_ns(
        command="single-session-apply", phase_task_id=ptk, session_uuid=uuid,
        version=1, result_json=str(_valid_result(tmp_project)),
    ), tmp_project)
    assert rc == 2


def test_apply_exit1_on_invalid_result(tmp_project):
    ptk, uuid = _claim_seed(tmp_project)
    bad = tmp_project / "bad.json"
    bad.write_text(json.dumps({"ok": True}), encoding="utf-8")  # missing keys
    rc = dispatch_single_session(_ns(
        command="single-session-apply", phase_task_id=ptk, session_uuid=uuid,
        version=1, result_json=str(bad),
    ), tmp_project)
    assert rc == 1


def test_apply_exit1_on_missing_result_file(tmp_project):
    ptk, uuid = _claim_seed(tmp_project)
    rc = dispatch_single_session(_ns(
        command="single-session-apply", phase_task_id=ptk, session_uuid=uuid,
        version=1, result_json=str(tmp_project / "nope.json"),
    ), tmp_project)
    assert rc == 1


def test_apply_exit1_on_unparseable_result_file(tmp_project):
    ptk, uuid = _claim_seed(tmp_project)
    broken = tmp_project / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    rc = dispatch_single_session(_ns(
        command="single-session-apply", phase_task_id=ptk, session_uuid=uuid,
        version=1, result_json=str(broken),
    ), tmp_project)
    assert rc == 1


# --- single-session-reload -------------------------------------------------

def test_reload_exit0_returns_context(tmp_project, capsys):
    _ss_config(tmp_project)
    rc = dispatch_single_session(_ns(command="single-session-reload"), tmp_project)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["context"]["mode"] == "single_session"
    assert "phaseSummaries" in out["context"]
    assert "summaryCharBudget" in out["context"]


def test_reload_exit1_on_no_config(tmp_project, capsys):
    rc = dispatch_single_session(_ns(command="single-session-reload"), tmp_project)
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "no_config"


# --- SS5 single-session-resume / -gate / -recover (exit-code map) ----------

def test_resume_exit0_on_resumable_run(tmp_project, capsys):
    _ss_config_with_loop_state(tmp_project)
    rc = dispatch_single_session(_ns(command="single-session-resume", confirm=False), tmp_project)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["action"] == "resume"


def test_resume_exit1_on_non_drivable_mode(tmp_project, capsys):
    _stale_config(tmp_project)
    rc = dispatch_single_session(_ns(command="single-session-resume", confirm=False), tmp_project)
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["action"] == "mode_unsupported"


def test_gate_exit0_pauses(tmp_project, capsys):
    cfg = _ss_config_with_loop_state(tmp_project)
    ptk = cfg["phase_tasks"][0]["phaseTaskId"]
    rc = dispatch_single_session(_ns(
        command="single-session-gate", phase_task_id=ptk, phase="project",
        split_id=None, state="pause",
    ), tmp_project)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["status"] == "paused_human_gate"


def test_gate_exit1_on_non_drivable_mode(tmp_project):
    _stale_config(tmp_project)
    rc = dispatch_single_session(_ns(
        command="single-session-gate", phase_task_id="ptk", phase="plan",
        split_id=None, state="pause",
    ), tmp_project)
    assert rc == 1


def test_recover_exit0_on_valid_task(tmp_project, capsys):
    cfg = _ss_config_with_loop_state(tmp_project)
    ptk = cfg["phase_tasks"][0]["phaseTaskId"]
    rc = dispatch_single_session(_ns(
        command="single-session-recover", phase_task_id=ptk, force_status="awaiting_launch",
    ), tmp_project)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_recover_exit1_on_non_drivable_mode(tmp_project):
    _stale_config(tmp_project)
    rc = dispatch_single_session(_ns(
        command="single-session-recover", phase_task_id="ptk", force_status="awaiting_launch",
    ), tmp_project)
    assert rc == 1


# --- cli.main routing (covers the cli.py dispatch branch) ------------------

def test_cli_main_routes_single_session_next(tmp_project, monkeypatch, capsys):
    _ss_config(tmp_project)
    monkeypatch.setattr(sys, "argv", [
        "orchestrator.py", "single-session-next", "--project-root", str(tmp_project),
    ])
    rc = cli_mod.main()
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["action"] == "dispatch"


def test_cli_main_routes_single_session_apply(tmp_project, monkeypatch, capsys):
    ptk, uuid = _claim_seed(tmp_project)
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", [
        "orchestrator.py", "single-session-apply",
        "--project-root", str(tmp_project), "--phase-task-id", ptk,
        "--session-uuid", uuid, "--version", "1",
        "--result-json", str(_valid_result(tmp_project)),
    ])
    rc = cli_mod.main()
    assert rc == 0


def test_cli_main_routes_single_session_reload(tmp_project, monkeypatch, capsys):
    _ss_config(tmp_project)
    monkeypatch.setattr(sys, "argv", [
        "orchestrator.py", "single-session-reload", "--project-root", str(tmp_project),
    ])
    rc = cli_mod.main()
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_main_routes_single_session_resume(tmp_project, monkeypatch, capsys):
    # Covers the cli.py argparse subparser + SINGLE_SESSION_COMMANDS routing for SS5.
    _ss_config_with_loop_state(tmp_project)
    monkeypatch.setattr(sys, "argv", [
        "orchestrator.py", "single-session-resume", "--project-root", str(tmp_project),
    ])
    rc = cli_mod.main()
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["action"] == "resume"

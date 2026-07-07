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


def _ss_config(project_root: Path, *, mode: str = "single_session"):
    return create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev", project_root, mode=mode,
    )


def _ns(**kw) -> argparse.Namespace:
    return argparse.Namespace(**kw)


def _valid_result(project_root: Path, phase: str = "project", *, ok: bool = True) -> Path:
    payload = {"ok": ok, "phase": phase, "summary": f"{phase} done",
               "artifacts": [f"artifacts/{phase}.md"]}
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


def test_next_exit1_on_wrong_mode(tmp_project, capsys):
    _ss_config(tmp_project, mode="multi_session")
    rc = dispatch_single_session(_ns(command="single-session-next"), tmp_project)
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["action"] == "wrong_mode"


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

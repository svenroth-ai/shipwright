"""Unit tests for the single-session orchestrator loop (Campaign 2026-07-07, SS3).

The loop (``orchestrator_pkg.single_session_loop``) drives a single_session run
in ONE conversation by REUSING ``phase_task_lifecycle`` — no bespoke completion
path, no direct run_config mutation. These tests pin:

  * resolve is a read-only guard (wrong_mode / no_config / terminal signals);
  * next_dispatch claims the frontier + records loop_state;
  * apply completes via the lifecycle, freezes splits after design (build
    fan-out), and strict-stops on ok=False (no successor);
  * a malformed result never reaches the lifecycle;
  * a stale CAS token is rejected fail-closed and leaves loop_state untouched;
  * the loop module mutates run_config ONLY through the lifecycle (ast guard).

The end-to-end pipeline walk (incl. multi-split fan-out) lives in
``integration-tests/test_single_session_pipeline.py``.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle  # noqa: E402
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from single_session.loop_state import load_loop_state  # noqa: E402
from single_session.result_contract import build_phase_runner_result  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _ss_config(project_root: Path):
    """Write a fresh single_session run config (seed = project task)."""
    return create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev",
        project_root, mode="single_session",
    )


def _result(phase: str, *, ok: bool = True, split_id: str | None = None):
    return build_phase_runner_result(
        ok=ok,
        phase=phase,
        summary=f"{phase} done" if ok else f"{phase} failed",
        artifacts=[f"artifacts/{phase}.md"],
        reason=None if ok else f"{phase} blew up",
        split_id=split_id,
    )


def _drive(project_root: Path, expected_phase: str, *, ok: bool = True,
           design_splits: list[str] | None = None):
    """next_dispatch -> (write design cfg) -> apply. Returns (dispatch, apply)."""
    nxt = loop.next_dispatch(project_root)
    assert nxt["action"] == "dispatch", nxt
    dispatch = nxt["dispatch"]
    assert dispatch["phase"] == expected_phase, dispatch

    if expected_phase == "design" and design_splits is not None:
        import json
        (project_root / "shipwright_design_config.json").write_text(
            json.dumps({"splits": design_splits}), encoding="utf-8",
        )

    applied = loop.apply_phase_result(
        project_root,
        phase_task_id=dispatch["phaseTaskId"],
        session_uuid=dispatch["sessionUuid"],
        expected_version=dispatch["version"],
        result=_result(expected_phase, ok=ok, split_id=dispatch["splitId"]),
    )
    return dispatch, applied


# --------------------------------------------------------------------------- #
# resolve — read-only guard
# --------------------------------------------------------------------------- #

def test_resolve_no_config_on_empty_dir(tmp_project):
    assert loop.resolve_next_dispatch(tmp_project)["action"] == "no_config"


def test_resolve_wrong_mode_on_multi_session(tmp_project):
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    res = loop.resolve_next_dispatch(tmp_project)
    assert res["action"] == "wrong_mode"
    assert res["mode"] == "multi_session"


def test_resolve_dispatches_project_on_fresh_single_session(tmp_project):
    _ss_config(tmp_project)
    res = loop.resolve_next_dispatch(tmp_project)
    assert res["action"] == "dispatch"
    assert res["dispatch"]["phase"] == "project"
    assert res["dispatch"]["splitId"] is None
    assert res["dispatch"]["slashCommand"] == "/shipwright-project"


def test_resolve_does_not_mutate_run_config(tmp_project):
    _ss_config(tmp_project)
    rc = tmp_project / "shipwright_run_config.json"
    before = rc.read_bytes()
    loop.resolve_next_dispatch(tmp_project)
    assert rc.read_bytes() == before


# --------------------------------------------------------------------------- #
# next_dispatch — claim + record loop_state
# --------------------------------------------------------------------------- #

def test_next_dispatch_claims_and_records_loop_state(tmp_project):
    config = _ss_config(tmp_project)
    seed_id = config["phase_tasks"][0]["phaseTaskId"]

    nxt = loop.next_dispatch(tmp_project)
    assert nxt["action"] == "dispatch"
    assert nxt["attempt"] == 1

    task = phase_task_lifecycle.get_phase_task(tmp_project, seed_id)["phase_task"]
    assert task["status"] == "in_progress"

    state = load_loop_state(tmp_project)
    assert state is not None
    assert state["currentPhaseTaskId"] == seed_id
    assert state["attempt"] == 1
    assert state["status"] == "running"


def test_next_dispatch_reclaim_is_idempotent(tmp_project):
    _ss_config(tmp_project)
    first = loop.next_dispatch(tmp_project)
    second = loop.next_dispatch(tmp_project)  # no apply between — re-dispatch
    assert second["action"] == "dispatch"
    assert second["idempotent"] is True
    assert second["dispatch"]["phaseTaskId"] == first["dispatch"]["phaseTaskId"]
    assert second["attempt"] == 2  # dispatch counter bumped, task not re-run


# --------------------------------------------------------------------------- #
# apply — complete via lifecycle + advance
# --------------------------------------------------------------------------- #

def test_apply_success_advances_pointer_and_resolves_next(tmp_project):
    _ss_config(tmp_project)
    dispatch, applied = _drive(tmp_project, "project")
    assert applied["ok"] is True
    assert applied["next"]["action"] == "dispatch"
    assert applied["next"]["dispatch"]["phase"] == "design"

    state = load_loop_state(tmp_project)
    assert state["lastCompletedPhaseTaskId"] == dispatch["phaseTaskId"]
    assert state["status"] == "running"
    assert state["attempt"] == 0  # reset for the fresh design task


def test_apply_design_freezes_splits_and_fans_out(tmp_project):
    _ss_config(tmp_project)
    _drive(tmp_project, "project")
    _dispatch, applied = _drive(
        tmp_project, "design", design_splits=["01-core", "02-ui"],
    )
    import json
    cfg = json.loads((tmp_project / "shipwright_run_config.json").read_text("utf-8"))
    assert cfg["splits_frozen"] == ["01-core", "02-ui"]
    assert cfg["runConditions"]["splitMode"] == "per_split"

    nxt = applied["next"]
    assert nxt["action"] == "dispatch"
    assert nxt["dispatch"]["phase"] == "plan"
    assert nxt["dispatch"]["splitId"] == "01-core"


def test_apply_failure_strict_stops_no_successor(tmp_project):
    _ss_config(tmp_project)
    _dispatch, applied = _drive(tmp_project, "project", ok=False)
    assert applied["ok"] is True  # complete-phase-task succeeded; failure is data
    assert applied["run_status"] == "failed"

    import json
    cfg = json.loads((tmp_project / "shipwright_run_config.json").read_text("utf-8"))
    assert cfg["status"] == "failed"
    assert all(t["phase"] != "design" for t in cfg["phase_tasks"]), "no successor planned"

    assert applied["next"]["action"] == "failed"
    assert load_loop_state(tmp_project)["status"] == "failed"


def test_apply_invalid_result_never_reaches_lifecycle(tmp_project):
    config = _ss_config(tmp_project)
    seed_id = config["phase_tasks"][0]["phaseTaskId"]
    nxt = loop.next_dispatch(tmp_project)
    dispatch = nxt["dispatch"]

    applied = loop.apply_phase_result(
        tmp_project,
        phase_task_id=dispatch["phaseTaskId"],
        session_uuid=dispatch["sessionUuid"],
        expected_version=dispatch["version"],
        result={"ok": True},  # missing phase/summary/artifacts — contract violation
    )
    assert applied["ok"] is False
    assert applied["reason"] == "invalid_result"
    assert applied["errors"]

    # Task untouched — still in_progress, run still in_progress.
    task = phase_task_lifecycle.get_phase_task(tmp_project, seed_id)["phase_task"]
    assert task["status"] == "in_progress"
    import json
    cfg = json.loads((tmp_project / "shipwright_run_config.json").read_text("utf-8"))
    assert cfg["status"] == "in_progress"


def test_apply_stale_version_fail_closed_leaves_loop_state(tmp_project):
    config = _ss_config(tmp_project)
    seed_id = config["phase_tasks"][0]["phaseTaskId"]
    nxt = loop.next_dispatch(tmp_project)
    dispatch = nxt["dispatch"]
    state_before = load_loop_state(tmp_project)

    # Another actor recovers the task — bumps version, releases the claim.
    phase_task_lifecycle.recover_phase_task(tmp_project, phase_task_id=seed_id)

    applied = loop.apply_phase_result(
        tmp_project,
        phase_task_id=dispatch["phaseTaskId"],
        session_uuid=dispatch["sessionUuid"],
        expected_version=dispatch["version"],  # now stale
        result=_result("project"),
    )
    assert applied["ok"] is False
    assert applied["reason"] == "stale_version"
    # loop_state pointer untouched by a rejected apply.
    assert load_loop_state(tmp_project)["status"] == state_before["status"] == "running"


# --------------------------------------------------------------------------- #
# no direct run_config mutation (ast guard) — mutation only via the lifecycle
# --------------------------------------------------------------------------- #

_FORBIDDEN_WRITERS = frozenset({
    "save_run_config", "atomic_write_json", "_write_config", "create_config",
})


def _code_identifiers(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def test_loop_modules_never_call_a_direct_run_config_writer():
    pkg_dir = Path(loop.__file__).resolve().parent
    for name in ("single_session_loop.py", "single_session_cli.py"):
        idents = _code_identifiers((pkg_dir / name).read_text(encoding="utf-8"))
        offenders = idents & _FORBIDDEN_WRITERS
        assert not offenders, (
            f"{name} calls a direct run_config writer {sorted(offenders)} — "
            f"single-session mutation must go through phase_task_lifecycle only"
        )

"""Terminal-state + degenerate-branch coverage for the single-session loop (SS3).

Split from ``test_single_session_loop.py`` (300-line test budget). Covers the
resolve branches a happy-path walk never reaches (needs_validation, blocked) and
the not-found pass-through in begin/apply.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from single_session.result_contract import build_phase_runner_result  # noqa: E402


def _ss_config(project_root: Path):
    return create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev",
        project_root, mode="single_session",
    )


def _load(project_root: Path) -> dict:
    return json.loads((project_root / "shipwright_run_config.json").read_text("utf-8"))


def _save(project_root: Path, cfg: dict) -> None:
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8",
    )


def test_resolve_needs_validation_lists_non_terminal(tmp_project):
    _ss_config(tmp_project)
    cfg = _load(tmp_project)
    cfg["status"] = "needs_validation"
    cfg["phase_tasks"][0]["status"] = "done"
    cfg["phase_tasks"].append({**cfg["phase_tasks"][0],
                               "phaseTaskId": "ptk-stuck", "phase": "test",
                               "status": "in_progress"})
    _save(tmp_project, cfg)
    res = loop.resolve_next_dispatch(tmp_project)
    assert res["action"] == "needs_validation"
    assert [b["phaseTaskId"] for b in res["blocked"]] == ["ptk-stuck"]


def test_resolve_blocked_when_no_frontier(tmp_project):
    _ss_config(tmp_project)
    cfg = _load(tmp_project)
    cfg["phase_tasks"][0]["status"] = "done"  # nothing awaiting/in_progress left
    _save(tmp_project, cfg)                     # status stays in_progress
    res = loop.resolve_next_dispatch(tmp_project)
    assert res == {"action": "blocked", "reason": "no_dispatchable_task"}


def test_begin_dispatch_not_found_passes_through(tmp_project):
    _ss_config(tmp_project)
    res = loop.begin_dispatch(tmp_project, phase_task_id="ptk-nope")
    assert res["ok"] is False
    assert res["reason"] == "not_found"


def test_apply_task_not_found_passes_through(tmp_project):
    _ss_config(tmp_project)
    res = loop.apply_phase_result(
        tmp_project, phase_task_id="ptk-nope", session_uuid="x",
        expected_version=1,
        result=build_phase_runner_result(
            ok=True, phase="project", summary="x", artifacts=["a/b.md"]),
    )
    assert res["ok"] is False
    assert res["reason"] == "not_found"

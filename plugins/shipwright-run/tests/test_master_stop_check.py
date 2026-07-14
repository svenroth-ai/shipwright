"""Tests for master_stop_check.py — observational master Stop hook.

Coverage:
    - No run config / v1 -> exit 0, no banner
    - v2 + pending tasks -> "in progress" banner
    - v2 + status complete -> "complete" banner
    - v2 + status failed -> "failed" banner with errors
    - Hook NEVER mutates state (purely observational).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO / "plugins" / "shipwright-run" / "scripts" / "hooks"))
sys.path.insert(0, str(_REPO / "plugins" / "shipwright-run" / "scripts" / "lib"))

from orchestrator import create_config  # noqa: E402

import master_stop_check  # noqa: E402


@pytest.fixture
def v2_project(tmp_path, monkeypatch):
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    create_config(
        scope="full_app", profile="supabase-nextjs",
        autonomy="guided", deploy_target="jelastic-dev",
        project_root=project,
    )
    return project


def _read_cfg(project_root):
    return json.loads(
        (project_root / "shipwright_run_config.json").read_text("utf-8"),
    )


def _write_cfg(project_root, cfg):
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8",
    )


def test_no_config(tmp_path, capsys):
    project = tmp_path / "empty"
    project.mkdir()
    rc = master_stop_check.run(project)
    assert rc == 0
    assert capsys.readouterr().err == ""


def test_v1_config_skips(tmp_path, capsys):
    project = tmp_path / "v1"
    project.mkdir()
    (project / "shipwright_run_config.json").write_text(
        json.dumps({"current_step": "project"}), encoding="utf-8",
    )
    rc = master_stop_check.run(project)
    assert rc == 0
    assert capsys.readouterr().err == ""


def test_in_progress_banner_lists_pending(v2_project, capsys):
    rc = master_stop_check.run(v2_project)
    assert rc == 0
    err = capsys.readouterr().err
    assert "Master Status" in err
    assert "in_progress" in err.lower() or "in progress" in err.lower()
    assert "project" in err  # the pending phase
    assert "PIPELINE COMPLETE" not in err
    assert "PIPELINE FAILED" not in err


def test_in_progress_banner_tells_the_user_to_reinvoke_run(v2_project, capsys):
    """The banner must NOT render a `claude --session-id` launch card.

    That card belonged to the removed multi-session engine: pasting it would start a
    bound phase session that claims a task nothing can complete. The master now DRIVES
    the pipeline, so the only correct resume instruction is "re-invoke /shipwright-run".
    """
    cfg = _read_cfg(v2_project)
    assert cfg["phase_tasks"][0]["status"] == "awaiting_launch"

    master_stop_check.run(v2_project)
    err = capsys.readouterr().err

    assert "--session-id" not in err, (
        "banner still renders a launch card for an engine that no longer exists"
    )
    assert "/shipwright-run" in err, "banner must tell the user how to resume"
    assert "IN PROGRESS" in err


def test_stale_multi_session_config_gets_a_migration_banner(v2_project, capsys):
    """A run config left on the removed mode must be named, not silently summarised."""
    cfg = _read_cfg(v2_project)
    cfg["mode"] = "multi_session"
    (v2_project / "shipwright_run_config.json").write_text(
        json.dumps(cfg, indent=2), encoding="utf-8",
    )

    master_stop_check.run(v2_project)
    err = capsys.readouterr().err

    assert "REMOVED" in err
    assert '"mode": "single_session"' in err, "banner must give the one-line fix"
    assert "migrations/multi-session-to-single-session.md" in err


def test_complete_banner(v2_project, capsys):
    cfg = _read_cfg(v2_project)
    cfg["phase_tasks"][0]["status"] = "done"
    cfg["status"] = "complete"
    _write_cfg(v2_project, cfg)
    rc = master_stop_check.run(v2_project)
    assert rc == 0
    err = capsys.readouterr().err
    assert "PIPELINE COMPLETE" in err


def test_failed_banner_includes_errors(v2_project, capsys):
    cfg = _read_cfg(v2_project)
    failed_ptk = cfg["phase_tasks"][0]["phaseTaskId"]
    cfg["phase_tasks"][0]["status"] = "failed"
    cfg["phase_tasks"][0]["errors"] = ["spec generation crashed"]
    cfg["status"] = "failed"
    _write_cfg(v2_project, cfg)
    rc = master_stop_check.run(v2_project)
    assert rc == 0
    err = capsys.readouterr().err
    assert "PIPELINE FAILED" in err
    assert "spec generation crashed" in err
    # Banner must render the FULL recover-phase-task command, including the
    # actual phaseTaskId — not just an instruction to "use orchestrator.py".
    assert "recover-phase-task" in err
    assert f"--phase-task-id {failed_ptk}" in err
    assert "uv run" in err
    assert "--force-status awaiting_launch" in err


def test_does_not_mutate_state(v2_project):
    """Critical: master_stop_check is observational only."""
    cfg_before = _read_cfg(v2_project)
    master_stop_check.run(v2_project)
    cfg_after = _read_cfg(v2_project)
    # Compare without updated_at (which save_run_config bumps — but we
    # never call save in master_stop_check)
    cfg_before.pop("updated_at", None)
    cfg_after.pop("updated_at", None)
    assert cfg_before == cfg_after

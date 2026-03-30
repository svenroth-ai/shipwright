"""Tests for orchestrator module."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import (
    PIPELINE_STEPS,
    _COMPLIANCE_SCRIPT,
    build_pipeline,
    create_config,
    get_build_progress,
    get_next_step,
    load_run_config,
    run_compliance_update,
    update_step,
)

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "lib" / "orchestrator.py")


def test_pipeline_includes_design():
    assert "design" in PIPELINE_STEPS
    assert PIPELINE_STEPS.index("design") == PIPELINE_STEPS.index("project") + 1


def test_create_config(tmp_project):
    config = create_config(
        scope="full_app",
        profile="supabase-nextjs",
        autonomy="guided",
        deploy_target="jelastic-dev",
        project_root=tmp_project,
    )
    assert config["scope"] == "full_app"
    assert config["profile"] == "supabase-nextjs"
    assert config["current_step"] == "project"
    assert config["pipeline"] == PIPELINE_STEPS
    assert (tmp_project / "shipwright_run_config.json").exists()


def test_get_next_step_fresh(tmp_project):
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    result = get_next_step(tmp_project)
    assert result["next_step"] == "project"


def test_get_next_step_after_project(tmp_project):
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    update_step(tmp_project, "project", "complete")

    result = get_next_step(tmp_project)
    assert result["next_step"] == "design"


def test_update_step_complete(tmp_project):
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    config = update_step(tmp_project, "project", "complete")

    assert "project" in config["completed_steps"]
    assert config["current_step"] == "design"


def test_update_step_all_complete(tmp_project):
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    for step in PIPELINE_STEPS:
        update_step(tmp_project, step, "complete")

    config = load_run_config(tmp_project)
    assert config["status"] == "complete"
    assert config["current_step"] is None

    result = get_next_step(tmp_project)
    assert result["next_step"] is None


def test_update_step_failed(tmp_project):
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    config = update_step(tmp_project, "build", "failed")
    assert config["status"] == "failed"
    assert config["current_step"] == "build"


def test_build_pipeline_without_aikido(monkeypatch):
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    pipeline = build_pipeline()
    assert "security" not in pipeline
    assert pipeline == PIPELINE_STEPS


def test_build_pipeline_with_aikido(monkeypatch):
    monkeypatch.setenv("AIKIDO_CLIENT_ID", "test-id")
    pipeline = build_pipeline()
    assert "security" in pipeline
    assert pipeline.index("security") == pipeline.index("test") + 1


def test_create_config_with_security(tmp_project, monkeypatch):
    monkeypatch.setenv("AIKIDO_CLIENT_ID", "test-id")
    config = create_config(
        scope="full_app",
        profile="supabase-nextjs",
        autonomy="guided",
        deploy_target="jelastic-dev",
        project_root=tmp_project,
    )
    assert "security" in config["pipeline"]
    assert config["pipeline"].index("security") == config["pipeline"].index("test") + 1


def test_compliance_runs_on_step_complete(tmp_project, mocker):
    """Compliance update is triggered when a step completes."""
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    mock_result = {"success": True, "phase": "project", "updated_reports": ["compliance/rtm.md"]}
    mocker.patch("orchestrator.run_compliance_update", return_value=mock_result)

    config = update_step(tmp_project, "project", "complete")
    assert config["last_compliance_update"]["phase"] == "project"
    assert "compliance/rtm.md" in config["last_compliance_update"]["reports"]


def test_compliance_skipped_on_failure(tmp_project, mocker):
    """Pipeline continues even if compliance update fails."""
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    mocker.patch("orchestrator.run_compliance_update", return_value=None)

    config = update_step(tmp_project, "project", "complete")
    assert "last_compliance_update" not in config
    assert "project" in config["completed_steps"]


def test_compliance_not_triggered_on_in_progress(tmp_project, mocker):
    """Compliance update should NOT run for in_progress status."""
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    mock_compliance = mocker.patch("orchestrator.run_compliance_update")
    update_step(tmp_project, "build", "in_progress")
    mock_compliance.assert_not_called()


def test_run_compliance_update_script_missing(tmp_project, mocker):
    """Returns None when compliance plugin is not installed."""
    mocker.patch("orchestrator._COMPLIANCE_SCRIPT", tmp_project / "nonexistent.py")
    result = run_compliance_update(tmp_project, "project")
    assert result is None


def test_get_next_step_no_config(tmp_path):
    result = get_next_step(tmp_path)
    assert result["next_step"] == "project"


def test_resume_midway(tmp_project):
    """Simulate interrupted pipeline and verify resume."""
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    # Complete first 4 steps (project, design, plan, build)
    update_step(tmp_project, "project", "complete")
    update_step(tmp_project, "design", "complete")
    update_step(tmp_project, "plan", "complete")
    update_step(tmp_project, "build", "complete")

    # Resume should point to "test"
    result = get_next_step(tmp_project)
    assert result["next_step"] == "test"
    assert set(result["completed"]) == {"project", "design", "plan", "build"}
    assert result["remaining"] == ["test", "deploy", "changelog"]


# --- CLI ---

# --- Build Progress ---

def test_get_build_progress_no_config(tmp_project):
    result = get_build_progress(tmp_project)
    assert result["total"] == 0
    assert result["completed"] == 0
    assert result["next_section"] is None
    assert result["all_done"] is False


def test_get_build_progress_partial(tmp_project):
    config = {
        "sections": [
            {"name": "01-auth", "status": "complete", "commit": "abc123"},
            {"name": "02-api", "status": "in_progress"},
            {"name": "03-ui", "status": "pending"},
        ]
    }
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    result = get_build_progress(tmp_project)
    assert result["total"] == 3
    assert result["completed"] == 1
    assert result["in_progress"] == 1
    assert result["next_section"] == "02-api"  # in_progress takes priority
    assert result["all_done"] is False
    assert result["completed_sections"] == ["01-auth"]


def test_get_build_progress_all_complete(tmp_project):
    config = {
        "sections": [
            {"name": "01-auth", "status": "complete", "commit": "abc"},
            {"name": "02-api", "status": "complete", "commit": "def"},
        ]
    }
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    result = get_build_progress(tmp_project)
    assert result["total"] == 2
    assert result["completed"] == 2
    assert result["next_section"] is None
    assert result["all_done"] is True


def test_get_build_progress_with_failed(tmp_project):
    config = {
        "sections": [
            {"name": "01-auth", "status": "complete", "commit": "abc"},
            {"name": "02-api", "status": "failed"},
            {"name": "03-ui", "status": "pending"},
        ]
    }
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    result = get_build_progress(tmp_project)
    assert result["completed"] == 1
    assert result["next_section"] == "03-ui"  # skips failed, picks pending


def test_get_build_progress_split_done_not_all_done(tmp_project):
    """Current split complete but more splits remain — split_done=True, all_done=False."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({
            "splits": [
                {"name": "01-auth", "status": "complete"},
                {"name": "02-dashboard", "status": "in_progress"},
            ],
        }), encoding="utf-8"
    )
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps({
            "current_split": "02-dashboard",
            "completed_splits": ["01-auth"],
            "split_01_sections": [
                {"name": "01-login", "status": "complete", "commit": "aaa"},
            ],
            "sections": [
                {"name": "01-widgets", "status": "complete", "commit": "bbb"},
                {"name": "02-charts", "status": "complete", "commit": "ccc"},
            ],
        }), encoding="utf-8"
    )
    result = get_build_progress(tmp_project)
    assert result["split_done"] is True
    assert result["all_done"] is True  # 1 completed + current = 2 = total_splits
    assert result["total_all"] == 3
    assert result["completed_all"] == 3


def test_get_build_progress_mid_split_with_more_splits(tmp_project):
    """Current split NOT complete, more splits exist."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({
            "splits": [
                {"name": "01-auth", "status": "complete"},
                {"name": "02-dashboard", "status": "in_progress"},
                {"name": "03-settings", "status": "pending"},
            ],
        }), encoding="utf-8"
    )
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps({
            "current_split": "02-dashboard",
            "completed_splits": ["01-auth"],
            "split_01_sections": [
                {"name": "01-login", "status": "complete", "commit": "aaa"},
            ],
            "sections": [
                {"name": "01-widgets", "status": "complete", "commit": "bbb"},
                {"name": "02-charts", "status": "pending"},
            ],
        }), encoding="utf-8"
    )
    result = get_build_progress(tmp_project)
    assert result["split_done"] is False
    assert result["all_done"] is False
    assert result["current_split"] == "02-dashboard"
    assert result["total_splits"] == 3
    assert result["total_all"] == 3
    assert result["completed_all"] == 2


def test_cli_get_build_progress(tmp_path):
    config = {
        "sections": [
            {"name": "01-auth", "status": "complete", "commit": "abc"},
            {"name": "02-api", "status": "pending"},
        ]
    }
    (tmp_path / "shipwright_build_config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, SCRIPT,
         "get-build-progress",
         "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    output = json.loads(result.stdout)
    assert output["total"] == 2
    assert output["next_section"] == "02-api"


# --- CLI ---

def test_cli_write_config(tmp_path):
    result = subprocess.run(
        [sys.executable, SCRIPT,
         "write-config",
         "--scope", "full_app",
         "--profile", "supabase-nextjs",
         "--autonomy", "guided",
         "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    output = json.loads(result.stdout)
    assert output["scope"] == "full_app"
    assert (tmp_path / "shipwright_run_config.json").exists()


def test_cli_get_next_step(tmp_path):
    subprocess.run(
        [sys.executable, SCRIPT,
         "write-config",
         "--scope", "full_app",
         "--project-root", str(tmp_path)],
        capture_output=True, encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, SCRIPT,
         "get-next-step",
         "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    output = json.loads(result.stdout)
    assert output["next_step"] == "project"

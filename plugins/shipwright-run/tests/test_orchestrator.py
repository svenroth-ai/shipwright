"""Tests for orchestrator module."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import (
    PIPELINE_STEPS,
    create_config,
    get_next_step,
    load_run_config,
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

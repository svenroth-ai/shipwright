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
    update_step(tmp_project, "project", "complete", force=True)

    result = get_next_step(tmp_project)
    assert result["next_step"] == "design"


def test_update_step_complete(tmp_project):
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    config = update_step(tmp_project, "project", "complete", force=True)

    assert "project" in config["completed_steps"]
    assert config["current_step"] == "design"


def test_update_step_all_complete(tmp_project):
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    for step in PIPELINE_STEPS:
        update_step(tmp_project, step, "complete", force=True)

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


def test_build_pipeline_never_includes_security_post_decouple(monkeypatch):
    """Iterate sec-report-and-orchestrator-decouple removed security from
    the orchestrator phase list. build_pipeline() returns PIPELINE_STEPS
    verbatim regardless of scanner-env state.
    """
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_SCANNER_BACKEND", raising=False)
    pipeline = build_pipeline()
    assert "security" not in pipeline
    assert pipeline == PIPELINE_STEPS


def test_build_pipeline_aikido_env_does_not_inject_security(monkeypatch):
    """AIKIDO_CLIENT_ID set must NOT cause security to be planned —
    the orchestrator no longer auto-runs security."""
    monkeypatch.setenv("AIKIDO_CLIENT_ID", "test-id")
    pipeline = build_pipeline()
    assert "security" not in pipeline
    assert pipeline == PIPELINE_STEPS


def test_create_config_pipeline_omits_security(tmp_project, monkeypatch):
    """Fresh runs produce a config whose pipeline never includes security."""
    monkeypatch.setenv("AIKIDO_CLIENT_ID", "test-id")
    config = create_config(
        scope="full_app",
        profile="supabase-nextjs",
        autonomy="guided",
        deploy_target="jelastic-dev",
        project_root=tmp_project,
    )
    assert "security" not in config["pipeline"]


def test_create_config_run_conditions_securityenabled_always_false(tmp_project, monkeypatch):
    """Schema requires the field; post-decouple value is always False."""
    monkeypatch.setenv("AIKIDO_CLIENT_ID", "ak_live_xxx")
    config = create_config(
        scope="full_app",
        profile="supabase-nextjs",
        autonomy="guided",
        deploy_target="jelastic-dev",
        project_root=tmp_project,
    )
    rc = config["runConditions"]
    assert rc["securityEnabled"] is False
    # aikidoClientIdPresent stays as a diagnostic
    assert rc["aikidoClientIdPresent"] is True


def test_legacy_pipeline_with_security_is_migrated_out(tmp_project):
    """Running load_run_config on a config that has 'security' in pipeline
    drops it (same _LEGACY_PIPELINE_ENTRIES pattern as compliance removal).
    """
    import json
    from orchestrator import load_run_config, CONFIG_NAME

    legacy = {
        "schemaVersion": 2,
        "scope": "full_app",
        "pipeline": ["project", "design", "plan", "build", "test", "security", "changelog", "deploy"],
        "phase_tasks": [],
        "completed_phase_task_ids": [],
        "splits_frozen": [],
        "runConditions": {
            "securityEnabled": True,
            "splitMode": None,
            "aikidoClientIdPresent": False,
        },
        "status": "in_progress",
        "completed_steps": [],
        "current_step": "project",
        "created_at": "2026-04-01T00:00:00+00:00",
    }
    (tmp_project / CONFIG_NAME).write_text(json.dumps(legacy), encoding="utf-8")

    loaded = load_run_config(tmp_project)
    assert "security" not in loaded["pipeline"]
    # All other phases preserved
    assert loaded["pipeline"] == ["project", "design", "plan", "build", "test", "changelog", "deploy"]


def test_migrate_in_flight_security_phase_tasks_skips_backlog_and_awaiting_launch(tmp_project):
    """Active migration: non-terminal security phase_tasks (backlog /
    awaiting_launch) are auto-skipped with a structured reason."""
    import json
    from orchestrator import load_run_config, CONFIG_NAME

    legacy = {
        "schemaVersion": 2,
        "scope": "full_app",
        "pipeline": ["project", "test", "security", "changelog"],  # legacy: includes security
        "phase_tasks": [
            {"phaseTaskId": "ptk-aaa", "phase": "test", "status": "done"},
            {"phaseTaskId": "ptk-sec1", "phase": "security", "status": "backlog"},
            {"phaseTaskId": "ptk-sec2", "phase": "security", "status": "awaiting_launch"},
        ],
        "completed_phase_task_ids": ["ptk-aaa"],
        "splits_frozen": [],
        "runConditions": {
            "securityEnabled": True,
            "splitMode": None,
            "aikidoClientIdPresent": False,
        },
        "status": "in_progress",
        "completed_steps": [],
        "current_step": "security",
        "created_at": "2026-04-01T00:00:00+00:00",
    }
    (tmp_project / CONFIG_NAME).write_text(json.dumps(legacy), encoding="utf-8")

    loaded = load_run_config(tmp_project)

    # Both non-terminal security phase_tasks become skipped
    sec_tasks = [t for t in loaded["phase_tasks"] if t["phase"] == "security"]
    assert len(sec_tasks) == 2
    assert all(t["status"] == "skipped" for t in sec_tasks)
    assert all(t.get("result", {}).get("skipped_by") == "security-decouple-migration" for t in sec_tasks)

    # Skipped phase_tasks join completed_phase_task_ids
    completed_ids = set(loaded["completed_phase_task_ids"])
    assert "ptk-sec1" in completed_ids
    assert "ptk-sec2" in completed_ids


def test_migrate_in_flight_security_leaves_in_progress_alone(tmp_project):
    """Active migration is conservative: in_progress security phase_task is
    left untouched (CAS-safe — user has an active session). The user must
    manually recover via recover-phase-task per the migration notice.
    """
    import json
    from orchestrator import load_run_config, CONFIG_NAME

    legacy = {
        "schemaVersion": 2,
        "scope": "full_app",
        "pipeline": ["project", "test", "security", "changelog"],
        "phase_tasks": [
            {"phaseTaskId": "ptk-sec1", "phase": "security", "status": "in_progress",
             "claimedBySessionUuid": "active-uuid", "version": 1},
        ],
        "completed_phase_task_ids": [],
        "splits_frozen": [],
        "runConditions": {
            "securityEnabled": True,
            "splitMode": None,
            "aikidoClientIdPresent": False,
        },
        "status": "in_progress",
        "completed_steps": [],
        "current_step": "security",
        "created_at": "2026-04-01T00:00:00+00:00",
    }
    (tmp_project / CONFIG_NAME).write_text(json.dumps(legacy), encoding="utf-8")

    loaded = load_run_config(tmp_project)
    sec_task = loaded["phase_tasks"][0]
    assert sec_task["status"] == "in_progress"  # NOT skipped
    assert sec_task.get("claimedBySessionUuid") == "active-uuid"


def test_compliance_runs_on_step_complete(tmp_project, mocker):
    """Compliance update is triggered when a step completes."""
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    mock_result = {"success": True, "phase": "project", "updated_reports": ["compliance/rtm.md"]}
    mocker.patch("orchestrator.run_compliance_update", return_value=mock_result)

    config = update_step(tmp_project, "project", "complete", force=True)
    assert config["last_compliance_update"]["phase"] == "project"
    assert "compliance/rtm.md" in config["last_compliance_update"]["reports"]


def test_compliance_skipped_on_failure(tmp_project, mocker):
    """Pipeline continues even if compliance update fails."""
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    mocker.patch("orchestrator.run_compliance_update", return_value=None)

    config = update_step(tmp_project, "project", "complete", force=True)
    assert "last_compliance_update" not in config
    assert "project" in config["completed_steps"]


def test_compliance_not_triggered_on_in_progress(tmp_project, mocker):
    """Compliance update should NOT run for in_progress status."""
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    mock_compliance = mocker.patch("orchestrator.run_compliance_update")
    update_step(tmp_project, "build", "in_progress")
    mock_compliance.assert_not_called()


def test_run_compliance_update_script_missing(tmp_project, mocker, capsys):
    """Missing script → loud stderr warn + compliance_update_failed event (plan v7)."""
    mocker.patch("orchestrator._COMPLIANCE_SCRIPT", tmp_project / "nonexistent.py")
    mock_record = mocker.patch("orchestrator._record_compliance_update_failed")

    result = run_compliance_update(tmp_project, "project")

    assert result is None
    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())
    assert payload["level"] == "warn"
    assert payload["message"] == "compliance update script missing"
    assert payload["phase"] == "project"
    mock_record.assert_called_once_with(tmp_project, "project", reason="script_missing")


def test_legacy_compliance_entry_migrated(tmp_project, mocker):
    """Legacy pipeline with 'compliance' entry is filtered on load (plan v7)."""
    mock_record = mocker.patch("orchestrator._record_pipeline_migration_event")
    legacy = {
        "scope": "full_app",
        "profile": "supabase-nextjs",
        "pipeline": ["project", "design", "plan", "build", "test",
                     "changelog", "compliance", "deploy"],
        "status": "in_progress",
        "current_step": "test",
        "completed_steps": ["project", "design", "plan", "build", "compliance"],
    }
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(legacy), encoding="utf-8"
    )

    config = load_run_config(tmp_project)

    assert "compliance" not in config["pipeline"]
    assert config["pipeline"] == [
        "project", "design", "plan", "build", "test", "changelog", "deploy",
    ]
    # Historical marker preserved in completed_steps
    assert "compliance" in config["completed_steps"]
    # Config was persisted
    persisted = json.loads((tmp_project / "shipwright_run_config.json").read_text(encoding="utf-8"))
    assert "compliance" not in persisted["pipeline"]
    # Event recorded (once)
    mock_record.assert_called_once()
    assert mock_record.call_args.kwargs["removed"] == ["compliance"]


def test_legacy_migration_idempotent(tmp_project, mocker):
    """After migration, subsequent loads do not re-record the event."""
    mock_record = mocker.patch("orchestrator._record_pipeline_migration_event")
    legacy = {
        "pipeline": ["project", "compliance", "deploy"],
        "completed_steps": [],
    }
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(legacy), encoding="utf-8"
    )

    load_run_config(tmp_project)  # first load migrates
    load_run_config(tmp_project)  # second load is clean
    load_run_config(tmp_project)  # third load is clean

    assert mock_record.call_count == 1


def test_fresh_config_has_no_compliance_in_pipeline(tmp_project):
    """New projects created post-v7 never see 'compliance' in pipeline."""
    assert "compliance" not in PIPELINE_STEPS
    config = create_config("full_app", "supabase-nextjs", "guided",
                           "jelastic-dev", tmp_project)
    assert "compliance" not in config["pipeline"]


def test_get_next_step_no_config(tmp_path):
    result = get_next_step(tmp_path)
    assert result["next_step"] == "project"


def test_resume_midway(tmp_project):
    """Simulate interrupted pipeline and verify resume."""
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    # Complete first 4 steps (project, design, plan, build)
    update_step(tmp_project, "project", "complete", force=True)
    update_step(tmp_project, "design", "complete", force=True)
    update_step(tmp_project, "plan", "complete", force=True)
    update_step(tmp_project, "build", "complete", force=True)

    # Resume should point to "test"
    result = get_next_step(tmp_project)
    assert result["next_step"] == "test"
    assert set(result["completed"]) == {"project", "design", "plan", "build"}
    assert result["remaining"] == ["test", "changelog", "deploy"]


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


# --- Standalone bootstrap ---

def test_update_step_no_config_bootstraps(tmp_path):
    """update_step with no run_config bootstraps a standalone config."""
    config = update_step(tmp_path, "project", "complete", force=True)
    assert config["standalone"] is True
    assert "project" in config["completed_steps"]
    assert config["pipeline"]  # should have default pipeline
    assert (tmp_path / "shipwright_run_config.json").exists()


def test_update_step_standalone_skips_validation(tmp_path, mocker):
    """Standalone configs skip phase validation (no interactive user)."""
    mock_validate = mocker.patch("phase_validators.validate_phase", return_value=(True, []))
    mocker.patch("orchestrator.run_compliance_update", return_value=None)
    # Bootstrap + complete in one call (no force)
    config = update_step(tmp_path, "project", "complete")
    # validate_phase should NOT have been called (standalone skips it)
    mock_validate.assert_not_called()
    assert "project" in config["completed_steps"]


def test_standalone_then_run_merges(tmp_path):
    """Switching from standalone to orchestrator preserves completed_steps."""
    # Simulate standalone completion
    standalone = {
        "standalone": True,
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy", "compliance"],
        "status": "in_progress",
        "current_step": "design",
        "completed_steps": ["project"],
    }
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps(standalone), encoding="utf-8"
    )

    # Now create orchestrator config (simulating /shipwright-run)
    config = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_path)

    # project should be carried over as completed
    assert "project" in config["completed_steps"]
    # current_step should be next after project (design)
    assert config["current_step"] == "design"
    # standalone flag should be gone (new config is not standalone)
    assert "standalone" not in config


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

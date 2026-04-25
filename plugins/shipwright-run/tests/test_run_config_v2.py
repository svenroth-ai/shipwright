"""Tests for v2 multi-session schema fields in shipwright_run_config.json.

F1 scope:
    - create_config writes schemaVersion=2, runId, runConditions, splits_frozen,
      completed_phase_task_ids, phase_tasks (with one initial project task).
    - is_v2_config helper recognises v2 configs.
    - phase_tasks[0] has the right shape for downstream F2 lifecycle subcommands.

Out of scope (F2+):
    - claim-phase-task / complete-phase-task lifecycle.
    - Hard-fail of v1 configs in phase-lifecycle subcommands.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import (  # noqa: E402
    SCHEMA_VERSION,
    create_config,
    is_v2_config,
    load_run_config,
)


# ---- is_v2_config ----


def test_is_v2_config_true_when_schema_version_2():
    assert is_v2_config({"schemaVersion": 2}) is True


def test_is_v2_config_false_when_v1_or_missing():
    assert is_v2_config({}) is False
    assert is_v2_config({"schemaVersion": 1}) is False
    assert is_v2_config({"schemaVersion": "2"}) is False  # strict int compare


# ---- create_config writes v2 schema ----


def test_create_config_writes_schema_version(tmp_project):
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    assert cfg["schemaVersion"] == SCHEMA_VERSION
    assert is_v2_config(cfg)


def test_create_config_writes_run_id(tmp_project):
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    assert re.fullmatch(r"run-[0-9a-f]{8}", cfg["runId"]), cfg["runId"]


def test_create_config_run_id_is_unique_per_call(tmp_project):
    a = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    b = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    assert a["runId"] != b["runId"]


def test_create_config_freezes_run_conditions(tmp_project):
    with mock.patch.dict("os.environ", {}, clear=False):
        # Drop AIKIDO_CLIENT_ID if present
        import os
        os.environ.pop("AIKIDO_CLIENT_ID", None)
        cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    rc = cfg["runConditions"]
    assert rc["securityEnabled"] is False
    assert rc["aikidoClientIdPresent"] is False
    assert rc["splitMode"] is None  # set later by freeze-splits


def test_create_config_aikido_id_sets_diagnostic_flag(tmp_project):
    """Iterate sec-report-and-orchestrator-decouple: securityEnabled is
    hardcoded False post-decouple. The aikidoClientIdPresent diagnostic
    still tracks AIKIDO_CLIENT_ID for WebUI display purposes.
    """
    with mock.patch.dict("os.environ", {"AIKIDO_CLIENT_ID": "ak_test_xxx"}, clear=False):
        cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    assert cfg["runConditions"]["securityEnabled"] is False
    assert cfg["runConditions"]["aikidoClientIdPresent"] is True


def test_create_config_writes_empty_splits_frozen(tmp_project):
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    assert cfg["splits_frozen"] == []


def test_create_config_initial_phase_tasks_has_project(tmp_project):
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    tasks = cfg["phase_tasks"]
    assert len(tasks) == 1
    t = tasks[0]
    assert t["phase"] == "project"
    assert t["splitId"] is None
    assert t["status"] == "awaiting_launch"
    assert t["version"] == 1
    assert t["executionCount"] == 0
    assert t["claimedBySessionUuid"] is None
    assert t["prerequisites"] == []
    assert t["slashCommand"] == "/shipwright-project"
    assert re.fullmatch(r"ptk-[0-9a-f]{8}", t["phaseTaskId"]), t["phaseTaskId"]
    # sessionUuid is a uuid4 — coarse format check
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        t["sessionUuid"],
    ), t["sessionUuid"]


def test_create_config_completed_phase_task_ids_empty_on_fresh_run(tmp_project):
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    assert cfg["completed_phase_task_ids"] == []


def test_create_config_persists_to_disk(tmp_project):
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    on_disk = json.loads((tmp_project / "shipwright_run_config.json").read_text(encoding="utf-8"))
    assert on_disk["schemaVersion"] == 2
    assert on_disk["runId"] == cfg["runId"]
    assert on_disk["phase_tasks"][0]["phaseTaskId"] == cfg["phase_tasks"][0]["phaseTaskId"]


def test_load_run_config_round_trip_preserves_v2_fields(tmp_project):
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    loaded = load_run_config(tmp_project)
    assert loaded["schemaVersion"] == 2
    assert loaded["runId"] == cfg["runId"]
    assert loaded["runConditions"] == cfg["runConditions"]
    assert loaded["phase_tasks"] == cfg["phase_tasks"]


# ---- v1 compat fields still present (until F2 hard-cut) ----


def test_create_config_keeps_v1_compat_fields(tmp_project):
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    # These are needed by the existing update_step / get_next_step until F2.
    assert "current_step" in cfg
    assert "completed_steps" in cfg
    assert cfg["current_step"] == "project"
    assert cfg["completed_steps"] == []


# ---- standalone-merge interaction ----


def test_create_config_skips_initial_task_when_standalone_already_completed_project(tmp_project):
    # Simulate a prior /shipwright-project run that wrote a standalone config
    standalone = {
        "standalone": True,
        "completed_steps": ["project"],
        "phase_history": {"project": {"foo": "bar"}},
    }
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(standalone), encoding="utf-8",
    )

    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    # phase_tasks still has the project entry but marked skipped (audit-trail)
    assert len(cfg["phase_tasks"]) == 1
    assert cfg["phase_tasks"][0]["phase"] == "project"
    assert cfg["phase_tasks"][0]["status"] == "skipped"
    assert cfg["phase_tasks"][0]["completedAt"] is not None
    assert cfg["completed_phase_task_ids"] == [cfg["phase_tasks"][0]["phaseTaskId"]]
    # phase_history carry-over preserved
    assert cfg["phase_history"] == {"project": {"foo": "bar"}}


# ---- JSON Schema file existence + basic shape ----


def test_v2_schema_json_file_exists():
    """The shared/schemas/run_config.v2.schema.json contract file must exist
    for the future shipwright-webui iterate to import."""
    repo_root = Path(__file__).resolve().parents[3]
    schema = repo_root / "shared" / "schemas" / "run_config.v2.schema.json"
    assert schema.exists(), schema

    data = json.loads(schema.read_text(encoding="utf-8"))
    assert data["$schema"].startswith("https://json-schema.org/draft/2020-12")
    assert data["properties"]["schemaVersion"]["const"] == 2
    # PhaseTask def must include ownership/CAS fields planned for F2
    pt = data["$defs"]["PhaseTask"]
    required = set(pt["required"])
    for field in ("phaseTaskId", "phase", "splitId", "sessionUuid",
                  "version", "status", "prerequisites", "executionCount"):
        assert field in required, f"PhaseTask missing required field: {field}"


def test_create_config_output_matches_schema_required_fields(tmp_project):
    """Structural sanity: create_config output declares every PhaseTask
    required field (subset check, not full json-schema validation)."""
    repo_root = Path(__file__).resolve().parents[3]
    schema = json.loads(
        (repo_root / "shared" / "schemas" / "run_config.v2.schema.json").read_text(encoding="utf-8"),
    )
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)

    config_required = set(schema["required"])
    for field in config_required:
        assert field in cfg, f"create_config missing top-level v2 field: {field}"

    pt_required = set(schema["$defs"]["PhaseTask"]["required"])
    task = cfg["phase_tasks"][0]
    for field in pt_required:
        assert field in task, f"phase_tasks[0] missing required field: {field}"

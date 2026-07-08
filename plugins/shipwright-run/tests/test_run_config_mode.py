"""Tests for the additive ``mode`` field in shipwright_run_config.json (SS1).

Campaign 2026-07-07-single-session-pipeline / SS1 mode-scaffold.

Scope (SS8, 2026-07-08 — single_session is now the sole/default mode):
    - schema carries an OPTIONAL ``mode`` (enum + default SINGLE_session; NOT in
      ``required`` so pre-SS1 configs still validate).
    - create_config writes ``mode`` (fresh default single_session; --mode overrides).
    - run_mode() reads back-compat: a mode-less/unknown config is STILL read as
      multi_session (the legacy fallback is deliberately separate from the fresh
      default, so flipping the default doesn't silently reinterpret old runs).
    - the write-config CLI exposes --mode with constrained choices (default single).

Out of scope: the single-session orchestrator loop that HONORS the mode (SS3).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import (  # noqa: E402
    DEFAULT_RUN_MODE,
    RUN_MODES,
    create_config,
    load_run_config,
    run_mode,
)


# ---- create_config writes mode ----


def test_create_config_default_mode_is_single_session(tmp_project):
    # SS8: a fresh run with no explicit --mode now defaults to single_session.
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    assert cfg["mode"] == "single_session"
    assert DEFAULT_RUN_MODE == "single_session"


def test_fresh_default_and_legacy_fallback_deliberately_diverge(tmp_project):
    """SS8 invariant: the FRESH-run default (single_session) is separate from the
    mode-less READ fallback (multi_session) — flipping the default must NOT
    silently reinterpret an existing mode-less run."""
    fresh = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    assert fresh["mode"] == "single_session"
    # A config predating the mode field is still read as multi_session.
    assert run_mode({"schemaVersion": 2, "runId": "run-legacy00"}) == "multi_session"


def test_create_config_single_session_mode(tmp_project):
    cfg = create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project,
        mode="single_session",
    )
    assert cfg["mode"] == "single_session"


def test_create_config_persists_mode_to_disk(tmp_project):
    create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project,
        mode="single_session",
    )
    on_disk = json.loads((tmp_project / "shipwright_run_config.json").read_text(encoding="utf-8"))
    assert on_disk["mode"] == "single_session"


def test_create_config_rejects_invalid_mode(tmp_project):
    with pytest.raises(ValueError):
        create_config(
            "full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project,
            mode="bogus",
        )


# ---- run_mode back-compat reader ----


def test_run_mode_defaults_missing_to_multi_session():
    # A config written before SS1 carries no ``mode`` — it is multi_session.
    assert run_mode({"schemaVersion": 2, "runId": "run-00000000"}) == "multi_session"


def test_run_mode_reads_explicit_single_session():
    assert run_mode({"mode": "single_session"}) == "single_session"


def test_run_mode_coerces_unknown_to_multi_session():
    # A hand-edited typo must never select an unbuilt execution path.
    assert run_mode({"mode": "sngle_sesion"}) == "multi_session"


def test_run_mode_covers_every_declared_mode():
    for m in RUN_MODES:
        assert run_mode({"mode": m}) == m


# ---- back-compat: legacy config loads unchanged ----


def test_legacy_config_without_mode_loads_and_reads_multi_session(tmp_project):
    """A v2 config predating SS1 (no ``mode`` key) loads unchanged and is
    read as multi_session — the pre-SS1 behaviour, uninterrupted."""
    legacy = {
        "schemaVersion": 2,
        "runId": "run-deadbeef",
        "scope": "full_app",
        "profile": None,
        "autonomy": "guided",
        "deploy_target": "jelastic-dev",
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
        "runConditions": {"securityEnabled": False, "splitMode": None, "aikidoClientIdPresent": False},
        "splits_frozen": [],
        "status": "in_progress",
        "completed_phase_task_ids": [],
        "phase_tasks": [],
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    (tmp_project / "shipwright_run_config.json").write_text(json.dumps(legacy), encoding="utf-8")

    loaded = load_run_config(tmp_project)
    assert "mode" not in loaded, "load must not inject a mode into a legacy config"
    assert run_mode(loaded) == "multi_session"


def test_load_run_config_round_trips_mode(tmp_project):
    cfg = create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project,
        mode="single_session",
    )
    loaded = load_run_config(tmp_project)
    assert loaded["mode"] == cfg["mode"] == "single_session"


# ---- schema contract ----


def _schema() -> dict:
    repo_root = Path(__file__).resolve().parents[3]
    return json.loads(
        (repo_root / "shared" / "schemas" / "run_config.v2.schema.json").read_text(encoding="utf-8"),
    )


def test_schema_declares_optional_mode_with_default():
    schema = _schema()
    mode = schema["properties"]["mode"]
    assert mode["enum"] == ["multi_session", "single_session"]
    # The JSON-Schema `default` is the ASSUME-WHEN-ABSENT value and MUST match the
    # code's absent-read fallback (run_mode -> multi_session), so a schema-default
    # consumer never reinterprets a mode-less legacy config. The fresh-WRITE default
    # (single_session) is code behaviour, asserted by the create_config tests above.
    assert mode["default"] == "multi_session"
    # OPTIONAL — back-compat: pre-SS1 configs (no mode) must still validate.
    assert "mode" not in schema["required"]


def test_schema_mode_enum_matches_run_modes():
    schema = _schema()
    assert tuple(schema["properties"]["mode"]["enum"]) == RUN_MODES


# ---- CLI exposes --mode ----


def test_write_config_cli_exposes_mode_choice():
    from orchestrator_pkg.cli import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "write-config", "--scope", "full_app", "--mode", "single_session",
    ])
    assert args.mode == "single_session"


def test_write_config_cli_defaults_mode_single_session():
    from orchestrator_pkg.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["write-config", "--scope", "full_app"])
    assert args.mode == "single_session"


def test_write_config_cli_rejects_unknown_mode():
    from orchestrator_pkg.cli import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["write-config", "--scope", "full_app", "--mode", "bogus"])

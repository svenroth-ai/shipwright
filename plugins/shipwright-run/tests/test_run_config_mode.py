"""Tests for the ``mode`` field in shipwright_run_config.json.

``single_session`` is the SOLE pipeline mode (``iterate-2026-07-14-remove-multi-session``).

THE INVARIANT these tests pin: a run is a **drivable** single-session pipeline **iff its
config records the explicit literal ``mode: "single_session"``**. Nothing is inferred.
The identical explicit-literal test is applied by ``gate_policy.read_run_config_mode``
(see ``shared/tests/test_gate_policy.py``), so the orchestrator loop and the phase-gate
mechanism can never disagree about whether a run is being driven.

Scope:
    - the schema carries a single-valued ``mode`` enum, still OPTIONAL (pre-SS1 configs
      must remain *readable*, even though they are not *drivable*);
    - ``create_config`` always writes the mode, and REJECTS the removed one;
    - ``is_single_session`` is the drivability predicate (explicit literal only);
    - the ``--mode`` CLI still ACCEPTS the removed literal at the argparse layer, so the
      handler can print the migration message instead of a generic "invalid choice".

The refusal behaviour of the execution entry points lives in
``test_non_drivable_config_guard.py``.
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
    is_legacy_multi_session,
    is_single_session,
    load_run_config,
    mode_rejection,
)


# ---- the mode set ----


def test_single_session_is_the_sole_mode():
    assert RUN_MODES == ("single_session",)
    assert DEFAULT_RUN_MODE == "single_session"


# ---- create_config ----


def test_create_config_default_mode_is_single_session(tmp_project):
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    assert cfg["mode"] == "single_session"


def test_create_config_persists_mode_to_disk(tmp_project):
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    on_disk = json.loads((tmp_project / "shipwright_run_config.json").read_text(encoding="utf-8"))
    assert on_disk["mode"] == "single_session"


def test_create_config_rejects_the_removed_multi_session_mode(tmp_project):
    """The factory must never seed a run under an engine that no longer exists — and it
    must say so, rather than raise an opaque enum error."""
    with pytest.raises(ValueError, match="multi_session"):
        create_config(
            "full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project,
            mode="multi_session",
        )
    assert not (tmp_project / "shipwright_run_config.json").exists(), (
        "a rejected mode must not leave a config behind"
    )


def test_create_config_rejects_invalid_mode(tmp_project):
    with pytest.raises(ValueError):
        create_config(
            "full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project,
            mode="bogus",
        )


# ---- is_single_session: the DRIVABILITY predicate (explicit literal only) ----


def test_is_single_session_requires_the_explicit_literal():
    assert is_single_session({"mode": "single_session"}) is True
    # Absent -> NOT drivable. This is the whole point: nothing is inferred.
    assert is_single_session({"schemaVersion": 2}) is False
    assert is_single_session({"mode": "multi_session"}) is False
    assert is_single_session({"mode": "sngle_sesion"}) is False


def test_is_legacy_multi_session_detects_the_removed_literal():
    assert is_legacy_multi_session({"mode": "multi_session"}) is True
    assert is_legacy_multi_session({"mode": "single_session"}) is False
    assert is_legacy_multi_session({}) is False


def test_mode_rejection_message_differs_by_cause_but_gives_one_fix():
    stale = mode_rejection({"mode": "multi_session"})
    modeless = mode_rejection({})
    assert stale["reason"] == modeless["reason"] == "mode_unsupported"
    # The stale-mode message names the removed engine; the mode-less one does not
    # accuse the user of a choice they never made.
    assert "REMOVED" in stale["message"] and "multi_session" in stale["message"]
    assert "multi_session" not in modeless["message"]
    # Both hand over the SAME one-line fix.
    for payload in (stale, modeless):
        assert '"mode": "single_session"' in payload["message"]
        assert "migrations/multi-session-to-single-session.md" in payload["message"]


# ---- a legacy config stays READABLE (only its execution is refused) ----


def test_legacy_config_without_mode_loads_unchanged(tmp_project):
    """A pre-SS1 v2 config must still LOAD — the guard is on the execution path, not the
    read path, so WebUI run history and .shipwright/runs/** stay inspectable."""
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
    assert is_single_session(loaded) is False, "and it must not be drivable"


def test_stale_multi_session_config_loads_without_raising(tmp_project):
    """Reading must never raise on the removed literal (Gemini review, high): a raise in
    the read path would crash read-only inspection of every historical run."""
    stale = {"schemaVersion": 2, "runId": "run-old", "mode": "multi_session", "phase_tasks": []}
    (tmp_project / "shipwright_run_config.json").write_text(json.dumps(stale), encoding="utf-8")
    loaded = load_run_config(tmp_project)
    assert loaded["mode"] == "multi_session"   # verbatim, not coerced
    assert is_single_session(loaded) is False  # ...and not drivable


def test_load_run_config_round_trips_mode(tmp_project):
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_project)
    loaded = load_run_config(tmp_project)
    assert loaded["mode"] == cfg["mode"] == "single_session"


# ---- schema contract (the WebUI renders this) ----


def _schema() -> dict:
    repo_root = Path(__file__).resolve().parents[3]
    return json.loads(
        (repo_root / "shared" / "schemas" / "run_config.v2.schema.json").read_text(encoding="utf-8"),
    )


def test_schema_mode_enum_is_single_valued():
    assert _schema()["properties"]["mode"]["enum"] == ["single_session"]


def test_schema_mode_declares_no_default():
    """ABSENCE IS MEANINGFUL: a mode-less config is "not a drivable run", which no
    default value can express. A `default` would let a schema-default consumer (ajv
    useDefaults — the WebUI is the named consumer of this contract) fill it in and
    thereby reinterpret a mode-less pre-SS1 config as drivable — the exact silent
    reinterpretation the explicit-literal rule exists to prevent.

    This SUPERSEDES the 2026-07-08 convention "schema default MUST equal the absent-read
    fallback" for this field: collapsing to one mode removed the read fallback, so there
    is no legal absent-value to publish. See conventions.md (2026-07-14).
    """
    assert "default" not in _schema()["properties"]["mode"], (
        "mode must declare NO default — absence means 'not drivable', not 'single_session'"
    )


def test_schema_mode_enum_matches_run_modes():
    assert tuple(_schema()["properties"]["mode"]["enum"]) == RUN_MODES


def test_schema_mode_stays_optional_for_readability():
    """Still not `required`: a pre-SS1 config must remain *readable* (it is refused at
    execution, not at parse)."""
    assert "mode" not in _schema()["required"]


# ---- CLI ----


def test_write_config_cli_defaults_mode_single_session():
    from orchestrator_pkg.cli import build_parser

    args = build_parser().parse_args(["write-config", "--scope", "full_app"])
    assert args.mode == "single_session"


def test_write_config_cli_does_not_advertise_the_removed_mode():
    """AC3: the flag must not OFFER it. `choices` carries only the real mode, so `--help`
    and the usage line never present multi_session as selectable."""
    from orchestrator_pkg.cli import build_parser

    action = next(a for a in build_parser()._subparsers._group_actions[0]
                  .choices["write-config"]._actions if a.dest == "mode")
    assert list(action.choices) == ["single_session"]


def test_write_config_cli_rejects_the_removed_literal_with_a_migration_message(capsys):
    """...but passing it must still SAY WHAT TO DO. argparse applies `type` before
    `choices`, so `_mode_value` intercepts the removed literal and raises the migration
    guidance instead of a bare "invalid choice: 'multi_session'" (Gemini review, medium —
    a user with a pre-removal config learns nothing from a generic enum error)."""
    from orchestrator_pkg.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args([
            "write-config", "--scope", "full_app", "--mode", "multi_session",
        ])
    err = capsys.readouterr().err
    assert "invalid choice" not in err
    assert '"mode": "single_session"' in err
    assert "migrations/multi-session-to-single-session.md" in err


def test_write_config_cli_rejects_unknown_mode():
    from orchestrator_pkg.cli import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["write-config", "--scope", "full_app", "--mode", "bogus"])

"""Tests for context_cost_readiness.py — autoCompactWindow + effort-level
readiness, same report shape (checks list, name + status + message) as
verify_local.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.context_cost_readiness as mod


@pytest.mark.covers("FR-01.20/AC06")
def test_unset_autocompact_window_warns():
    """FR-01.20/AC06 — "left unset... is reported as a finding... never
    silently accepted."""
    result = mod.check_autocompact_window(None, "claude-sonnet-5")
    assert result["status"] == "warn"


@pytest.mark.covers("FR-01.20/AC06")
def test_autocompact_window_above_model_context_window_warns():
    """FR-01.20/AC06 — "set above what the active model's context window
    allows... is reported as a finding."""
    result = mod.check_autocompact_window(2_000_000, "claude-sonnet-5")  # window is 1M
    assert result["status"] == "warn"


@pytest.mark.covers("FR-01.20/AC06")
def test_sane_autocompact_window_passes():
    """Negative case for AC06's autoCompactWindow clause: a sane setting is
    NOT reported as a finding."""
    result = mod.check_autocompact_window(500_000, "claude-sonnet-5")  # window is 1M
    assert result["status"] == "pass"


def test_autocompact_window_set_without_a_model_warns_not_fabricated():
    # No --model given: this script has no way to know the active model, so
    # it must say so rather than silently assuming one (same "never guess"
    # rule model_pricing.py applies to an unrecognized model id).
    result = mod.check_autocompact_window(500_000, None)
    assert result["status"] == "warn"
    assert "no --model" in result["message"] or "--model" in result["message"]


def test_unrecognized_model_id_warns_not_crashes():
    result = mod.check_autocompact_window(500_000, "claude-nonexistent-model")
    assert result["status"] == "warn"


def test_versioned_snapshot_model_id_resolves_the_same_as_its_family():
    # External-review finding: a real transcript records the dated snapshot
    # id (e.g. "claude-sonnet-5-20260612"), not the bare family name -- this
    # must resolve via the same policy as model_pricing.resolve_model_id,
    # not warn "not a known model" for an actual live model.
    result = mod.check_autocompact_window(500_000, "claude-sonnet-5-20260612")
    assert result["status"] == "pass"
    assert "1,000,000" in result["message"]


@pytest.mark.covers("FR-01.20/AC06")
def test_effort_level_unspecified_warns():
    """FR-01.20/AC06 — "its reasoning-effort level is worth flagging... is
    reported as a finding."""
    result = mod.check_effort_level(None)
    assert result["status"] == "warn"


@pytest.mark.covers("FR-01.20/AC06")
def test_effort_level_recognized_value_passes():
    result = mod.check_effort_level("high")
    assert result["status"] == "pass"


@pytest.mark.covers("FR-01.20/AC06")
def test_effort_level_unrecognized_value_warns():
    result = mod.check_effort_level("extreme")
    assert result["status"] == "warn"


def test_settings_hierarchy_local_project_overrides_shared_overrides_user(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    (home / ".claude").mkdir(parents=True)
    (project / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"autoCompactWindow": 100_000}), encoding="utf-8"
    )
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"autoCompactWindow": 200_000}), encoding="utf-8"
    )
    (project / ".claude" / "settings.local.json").write_text(
        json.dumps({"autoCompactWindow": 300_000}), encoding="utf-8"
    )

    settings = mod.read_settings_hierarchy(project, home=home)

    assert settings["autoCompactWindow"] == 300_000  # local-project wins


def test_settings_hierarchy_missing_files_is_empty_not_a_crash(tmp_path):
    settings = mod.read_settings_hierarchy(tmp_path / "project", home=tmp_path / "home")
    assert settings == {}


def test_settings_hierarchy_malformed_json_is_skipped_not_a_crash(tmp_path):
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text("not json", encoding="utf-8")

    settings = mod.read_settings_hierarchy(project, home=tmp_path / "home")

    assert settings == {}


@pytest.mark.covers("FR-01.20/AC06")
def test_run_readiness_checks_returns_both_checks():
    checks = mod.run_readiness_checks({"autoCompactWindow": 500_000}, "claude-sonnet-5", "high")
    names = {c["name"] for c in checks}
    assert names == {"autoCompactWindow", "effort level"}


@pytest.mark.covers("FR-01.20/AC06")
def test_main_prints_checks_json(tmp_path, capsys, monkeypatch):
    """FR-01.20/AC06 — "reported... in the same reported shape as the
    project's existing pre-push checks": a list of named checks, each with a
    pass/warn status and a message (module docstring; see also
    verify_local.py's own check registry)."""
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    rc = mod.main(["--model", "claude-sonnet-5", "--effort", "high"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["checks"]) == 2
    assert all(c["status"] in ("pass", "warn") for c in out["checks"])
    assert all({"name", "status", "message"} <= c.keys() for c in out["checks"])

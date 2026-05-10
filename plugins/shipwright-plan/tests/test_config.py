"""Tests for shipwright-plan config module.

External-review config helpers (get_external_review_status,
is_external_review_enabled) live in shared/scripts/lib/external_review_config.py
since v0.5.x and are exercised in shared/tests/test_external_review_config.py.
"""

from lib.config import (
    _deep_merge,
    is_e2e_enabled,
    load_global_config,
)


def test_load_global_config(plugin_root):
    config = load_global_config(plugin_root)
    # Plan-local config retains context, e2e_test_plan, vertex_ai.
    assert "e2e_test_plan" in config
    assert "context" in config
    # Review-related keys (models, external_review, llm_client) moved to shared.
    assert "models" not in config
    assert "external_review" not in config
    assert "llm_client" not in config


def test_load_missing_config(tmp_path):
    config = load_global_config(tmp_path / "nonexistent")
    assert config == {}


def test_deep_merge():
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99}, "e": 5}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": {"c": 99, "d": 3}, "e": 5}


def test_is_e2e_enabled_default():
    assert is_e2e_enabled({}) is True


def test_is_e2e_disabled():
    assert is_e2e_enabled({"e2e_test_plan": {"enabled": False}}) is False

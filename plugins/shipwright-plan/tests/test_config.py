"""Tests for shipwright-plan config module."""

from lib.config import (
    _deep_merge,
    get_external_review_status,
    is_e2e_enabled,
    is_external_review_enabled,
    load_global_config,
    load_session_config,
    save_session_config,
)


def test_load_global_config(plugin_root):
    config = load_global_config(plugin_root)
    assert "models" in config
    assert "gemini" in config["models"]
    assert "external_review" in config
    assert "e2e_test_plan" in config


def test_load_missing_config(tmp_path):
    config = load_global_config(tmp_path / "nonexistent")
    assert config == {}


def test_session_config_roundtrip(tmp_planning):
    save_session_config(tmp_planning, {"test": "value"})
    loaded = load_session_config(tmp_planning)
    assert loaded["test"] == "value"


def test_deep_merge():
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99}, "e": 5}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": {"c": 99, "d": 3}, "e": 5}


def test_is_external_review_disabled_by_config():
    config = {"external_review": {"feedback_iterations": 0}}
    assert is_external_review_enabled(config) is False


def test_is_external_review_disabled_no_keys(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config = {"external_review": {"feedback_iterations": 1}}
    assert is_external_review_enabled(config) is False


def test_is_external_review_enabled_openrouter(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-123")
    config = {"external_review": {"feedback_iterations": 1}}
    assert is_external_review_enabled(config) is True


def test_get_external_review_status_user_disabled():
    config = {"external_review": {"feedback_iterations": 0}}
    assert get_external_review_status(config) == "user_disabled"


def test_get_external_review_status_missing_keys(monkeypatch, tmp_path):
    # Isolate from repo .env.local by chdir-ing to an empty tmp dir
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config = {"external_review": {"feedback_iterations": 1}}
    assert get_external_review_status(config) == "missing_keys"


def test_get_external_review_status_available_openrouter(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-123")
    config = {"external_review": {"feedback_iterations": 1}}
    assert get_external_review_status(config) == "available"


def test_is_e2e_enabled_default():
    assert is_e2e_enabled({}) is True


def test_is_e2e_disabled():
    assert is_e2e_enabled({"e2e_test_plan": {"enabled": False}}) is False

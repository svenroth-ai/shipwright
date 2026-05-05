"""Tests for shared external review config module.

Covers:
- load_review_config()
- is_external_review_enabled(config)
- get_external_review_status(config)
- resolve_model(config, model_key) — incl. SHIPWRIGHT_REVIEW_MODEL_* env-overrides
"""

import json

import pytest

from lib.external_review_config import (
    get_external_review_status,
    is_external_code_review_enabled,
    is_external_review_enabled,
    load_review_config,
    resolve_model,
)


# ---- Fixtures ----

@pytest.fixture
def sample_config_dict():
    return {
        "external_review": {"alert_if_missing": True, "feedback_iterations": 1},
        "models": {
            "gemini": "gemini-test-default",
            "chatgpt": "gpt-test-default",
            "openrouter_gemini": "google/gemini-test-default",
            "openrouter_chatgpt": "openai/gpt-test-default",
        },
        "llm_client": {"timeout_seconds": 120, "max_retries": 3},
    }


@pytest.fixture
def sample_config_path(tmp_path, sample_config_dict):
    path = tmp_path / "external_review.json"
    path.write_text(json.dumps(sample_config_dict), encoding="utf-8")
    return path


@pytest.fixture
def clean_review_env(monkeypatch, tmp_path):
    """Strip all review-related env vars + chdir to empty dir to avoid .env.local pickup."""
    monkeypatch.chdir(tmp_path)
    for key in (
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "SHIPWRIGHT_REVIEW_MODEL_GEMINI",
        "SHIPWRIGHT_REVIEW_MODEL_CHATGPT",
        "SHIPWRIGHT_REVIEW_MODEL_OPENROUTER_GEMINI",
        "SHIPWRIGHT_REVIEW_MODEL_OPENROUTER_CHATGPT",
    ):
        monkeypatch.delenv(key, raising=False)


# ---- load_review_config ----

def test_load_review_config_real_default():
    """Default path resolves to shared/config/external_review.json (real shipping config)."""
    config = load_review_config()
    assert "external_review" in config
    assert "models" in config
    assert "llm_client" in config


def test_load_review_config_explicit_path(sample_config_path, sample_config_dict):
    loaded = load_review_config(sample_config_path)
    assert loaded == sample_config_dict


def test_load_review_config_missing_returns_empty(tmp_path):
    config = load_review_config(tmp_path / "nonexistent.json")
    assert config == {}


# ---- per-project shipwright_iterate_config.json deep-merge -----------

def _seed_project(tmp_path, iterate_config: dict | None = None):
    """Seed a tmp directory with a shipwright_run_config.json marker
    (so auto-discovery finds it) and optionally a per-project iterate
    config. Returns the project root path.
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    if iterate_config is not None:
        (proj / "shipwright_iterate_config.json").write_text(
            json.dumps(iterate_config), encoding="utf-8",
        )
    return proj


def test_load_review_config_explicit_project_root_overrides_feedback_iterations(
    sample_config_path, sample_config_dict, tmp_path,
):
    """Per-project shipwright_iterate_config.json overrides
    external_review.feedback_iterations from the shared default.
    """
    proj = _seed_project(tmp_path, {"external_review": {"feedback_iterations": 0}})
    merged = load_review_config(sample_config_path, project_root=proj)
    assert merged["external_review"]["feedback_iterations"] == 0
    # Sibling keys in the same sub-dict survive the deep-merge (NOT replaced)
    assert merged["external_review"]["alert_if_missing"] is True
    # Top-level untouched keys survive
    assert merged["models"] == sample_config_dict["models"]


def test_load_review_config_project_root_adds_external_code_review_field(
    sample_config_path, tmp_path,
):
    """The per-project file can introduce external_code_review.enabled,
    which is absent from the shared default.
    """
    proj = _seed_project(tmp_path, {"external_code_review": {"enabled": False}})
    merged = load_review_config(sample_config_path, project_root=proj)
    assert merged["external_code_review"]["enabled"] is False


def test_load_review_config_no_per_project_file_returns_default(
    sample_config_path, sample_config_dict, tmp_path,
):
    """If shipwright_iterate_config.json is absent, the shared default is
    returned unchanged.
    """
    proj = _seed_project(tmp_path, iterate_config=None)
    merged = load_review_config(sample_config_path, project_root=proj)
    assert merged == sample_config_dict


def test_load_review_config_round_trip_per_project_overrides(
    sample_config_path, tmp_path,
):
    """Boundary probe: write the per-project file with the schema produced
    by config_writer.write_iterate_config (adopt), read it through
    load_review_config, assert the loaded values match the file. Closes
    the producer→file→consumer chain that ADR-032 added to the producer
    side and this iterate adds to the consumer side.
    """
    iterate_cfg = {
        "external_review": {"feedback_iterations": 0},
        "external_code_review": {"enabled": True},
        "seeded_by_adopt": True,
        "updated_at": "2026-05-06T00:00:00+00:00",
    }
    proj = _seed_project(tmp_path, iterate_cfg)

    # Re-read raw file from disk to confirm what we wrote
    raw = (proj / "shipwright_iterate_config.json").read_text(encoding="utf-8")
    on_disk = json.loads(raw)
    assert on_disk == iterate_cfg

    merged = load_review_config(sample_config_path, project_root=proj)
    # Type fidelity round-trip
    assert isinstance(merged["external_review"]["feedback_iterations"], int)
    assert isinstance(merged["external_code_review"]["enabled"], bool)
    assert merged["external_review"]["feedback_iterations"] == 0
    assert merged["external_code_review"]["enabled"] is True


def test_load_review_config_malformed_per_project_file_logs_and_falls_back(
    sample_config_path, sample_config_dict, tmp_path, capsys,
):
    """A malformed per-project file must NOT crash the loader. The shared
    default returns unchanged and the loader emits a stderr warning so
    operators see why their override didn't take effect.
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    (proj / "shipwright_iterate_config.json").write_text("{not-json", encoding="utf-8")
    merged = load_review_config(sample_config_path, project_root=proj)
    assert merged == sample_config_dict
    captured = capsys.readouterr()
    assert "shipwright_iterate_config.json" in captured.err


# ---- is_external_code_review_enabled ----

def test_is_external_code_review_enabled_default_true(clean_review_env):
    """Cascade defaults to enabled when the field is absent — matches the
    Branch C documentation in iteration-reviews.md (cascade ON unless
    explicitly opted out).
    """
    assert is_external_code_review_enabled({}) is True
    assert is_external_code_review_enabled({"external_review": {"feedback_iterations": 1}}) is True


def test_is_external_code_review_enabled_explicit_false(clean_review_env):
    """external_code_review.enabled: false disables the cascade."""
    config = {"external_code_review": {"enabled": False}}
    assert is_external_code_review_enabled(config) is False


def test_is_external_code_review_enabled_explicit_true(clean_review_env):
    config = {"external_code_review": {"enabled": True}}
    assert is_external_code_review_enabled(config) is True


def test_is_external_code_review_independent_of_feedback_iterations(clean_review_env):
    """Per iteration-reviews.md:191-194: the cascade gate is independent
    of plan/iterate-mode external_review.feedback_iterations. A user
    can disable plan/iterate review while keeping the cascade on, and
    vice versa.
    """
    config = {
        "external_review": {"feedback_iterations": 0},  # plan/iterate disabled
        "external_code_review": {"enabled": True},      # cascade still on
    }
    assert is_external_code_review_enabled(config) is True

    config2 = {
        "external_review": {"feedback_iterations": 1},   # plan/iterate enabled
        "external_code_review": {"enabled": False},      # cascade explicitly off
    }
    assert is_external_code_review_enabled(config2) is False


# ---- is_external_review_enabled ----

def test_is_external_review_disabled_by_config(clean_review_env):
    config = {"external_review": {"feedback_iterations": 0}}
    assert is_external_review_enabled(config) is False


def test_is_external_review_disabled_no_keys(clean_review_env):
    config = {"external_review": {"feedback_iterations": 1}}
    assert is_external_review_enabled(config) is False


def test_is_external_review_enabled_openrouter(monkeypatch, clean_review_env):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-123")
    config = {"external_review": {"feedback_iterations": 1}}
    assert is_external_review_enabled(config) is True


def test_is_external_review_enabled_gemini_direct(monkeypatch, clean_review_env):
    monkeypatch.setenv("GEMINI_API_KEY", "AI-test-123")
    config = {"external_review": {"feedback_iterations": 1}}
    assert is_external_review_enabled(config) is True


def test_is_external_review_enabled_openai_direct(monkeypatch, clean_review_env):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-123")
    config = {"external_review": {"feedback_iterations": 1}}
    assert is_external_review_enabled(config) is True


# ---- get_external_review_status ----

def test_get_external_review_status_user_disabled(clean_review_env):
    config = {"external_review": {"feedback_iterations": 0}}
    assert get_external_review_status(config) == "user_disabled"


def test_get_external_review_status_missing_keys(clean_review_env):
    config = {"external_review": {"feedback_iterations": 1}}
    assert get_external_review_status(config) == "missing_keys"


def test_get_external_review_status_available_openrouter(monkeypatch, clean_review_env):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-123")
    config = {"external_review": {"feedback_iterations": 1}}
    assert get_external_review_status(config) == "available"


def test_get_external_review_status_default_iterations_is_1(clean_review_env):
    """No explicit feedback_iterations -> defaults to 1 -> behaves like enabled."""
    config = {}  # no external_review block at all
    assert get_external_review_status(config) == "missing_keys"


# ---- resolve_model — defaults ----

def test_resolve_model_default_gemini(clean_review_env):
    config = {"models": {"gemini": "gemini-3.1-pro-preview"}}
    assert resolve_model(config, "gemini") == "gemini-3.1-pro-preview"


def test_resolve_model_default_chatgpt(clean_review_env):
    config = {"models": {"chatgpt": "gpt-5.4"}}
    assert resolve_model(config, "chatgpt") == "gpt-5.4"


def test_resolve_model_default_openrouter_gemini(clean_review_env):
    config = {"models": {"openrouter_gemini": "google/gemini-3.1-pro-preview"}}
    assert resolve_model(config, "openrouter_gemini") == "google/gemini-3.1-pro-preview"


def test_resolve_model_default_openrouter_chatgpt(clean_review_env):
    config = {"models": {"openrouter_chatgpt": "openai/gpt-5.4"}}
    assert resolve_model(config, "openrouter_chatgpt") == "openai/gpt-5.4"


# ---- resolve_model — env overrides ----

def test_resolve_model_env_override_gemini(monkeypatch, clean_review_env):
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_MODEL_GEMINI", "custom-gemini-2")
    config = {"models": {"gemini": "config-default"}}
    assert resolve_model(config, "gemini") == "custom-gemini-2"


def test_resolve_model_env_override_chatgpt(monkeypatch, clean_review_env):
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_MODEL_CHATGPT", "custom-chatgpt-2")
    config = {"models": {"chatgpt": "config-default"}}
    assert resolve_model(config, "chatgpt") == "custom-chatgpt-2"


def test_resolve_model_env_override_openrouter_gemini(monkeypatch, clean_review_env):
    monkeypatch.setenv(
        "SHIPWRIGHT_REVIEW_MODEL_OPENROUTER_GEMINI",
        "anthropic/claude-opus-4-7",
    )
    config = {"models": {"openrouter_gemini": "config-default"}}
    assert resolve_model(config, "openrouter_gemini") == "anthropic/claude-opus-4-7"


def test_resolve_model_env_override_openrouter_chatgpt(monkeypatch, clean_review_env):
    monkeypatch.setenv(
        "SHIPWRIGHT_REVIEW_MODEL_OPENROUTER_CHATGPT",
        "qwen/qwen-coder",
    )
    config = {"models": {"openrouter_chatgpt": "config-default"}}
    assert resolve_model(config, "openrouter_chatgpt") == "qwen/qwen-coder"


# ---- resolve_model — defensive (whitespace, empty, invalid) ----

def test_resolve_model_empty_string_falls_back(monkeypatch, clean_review_env):
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_MODEL_GEMINI", "")
    config = {"models": {"gemini": "config-default"}}
    assert resolve_model(config, "gemini") == "config-default"


def test_resolve_model_whitespace_only_falls_back(monkeypatch, clean_review_env):
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_MODEL_GEMINI", "   \t  \n")
    config = {"models": {"gemini": "config-default"}}
    assert resolve_model(config, "gemini") == "config-default"


def test_resolve_model_env_value_is_stripped(monkeypatch, clean_review_env):
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_MODEL_GEMINI", "  trimmed-model  ")
    config = {"models": {"gemini": "config-default"}}
    assert resolve_model(config, "gemini") == "trimmed-model"


def test_resolve_model_invalid_key_raises(clean_review_env):
    config = {"models": {"invalid": "x"}}
    with pytest.raises(ValueError, match="Invalid model key"):
        resolve_model(config, "invalid")


def test_resolve_model_returns_empty_when_not_in_config(clean_review_env):
    config = {}  # no models block
    assert resolve_model(config, "gemini") == ""

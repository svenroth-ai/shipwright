"""Tests for shipwright-build config."""

from lib.config import DEFAULTS, load_build_config, save_build_config


def test_load_defaults(tmp_path):
    config = load_build_config(tmp_path)
    assert config == DEFAULTS
    assert config["auto_push"] is False
    assert config["conventional_commits"] is True
    assert config["migration_safety"] is True


def test_load_with_overrides(tmp_project_with_config):
    config = load_build_config(tmp_project_with_config)
    assert config["auto_push"] is False
    assert config["conventional_commits"] is True


def test_save_and_load(tmp_path):
    config = {"auto_push": True, "custom": "value"}
    save_build_config(tmp_path, config)
    loaded = load_build_config(tmp_path)
    assert loaded["auto_push"] is True
    assert loaded["custom"] == "value"

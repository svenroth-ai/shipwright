"""Tests for shared config handling."""

import json

from lib.config import (
    CONFIG_FILES,
    get_config_path,
    read_all_configs,
    read_config,
    update_config,
    write_config,
)


def test_get_config_path(tmp_project):
    path = get_config_path("run", tmp_project)
    assert path.name == "shipwright_run_config.json"
    assert path.parent == tmp_project


def test_get_config_path_invalid_skill(tmp_project):
    import pytest

    with pytest.raises(ValueError, match="Unknown skill"):
        get_config_path("invalid", tmp_project)


def test_read_config_missing(tmp_project):
    result = read_config("run", tmp_project)
    assert result == {}


def test_write_and_read_config(tmp_project):
    data = {"scope": "full_app", "profile": "supabase-nextjs"}
    write_config("run", tmp_project, data)

    result = read_config("run", tmp_project)
    assert result == data


def test_update_config_creates_if_missing(tmp_project):
    result = update_config("run", tmp_project, {"scope": "extension"})
    assert result == {"scope": "extension"}

    # Verify persisted
    assert read_config("run", tmp_project) == {"scope": "extension"}


def test_update_config_merges(tmp_project):
    write_config("run", tmp_project, {"scope": "full_app", "profile": "supabase-nextjs"})
    result = update_config("run", tmp_project, {"autonomy_level": 2})
    assert result == {"scope": "full_app", "profile": "supabase-nextjs", "autonomy_level": 2}


def test_read_all_configs_empty(tmp_project):
    result = read_all_configs(tmp_project)
    assert set(result.keys()) == set(CONFIG_FILES.keys())
    assert all(v == {} for v in result.values())


def test_read_all_configs_with_data(project_with_configs):
    result = read_all_configs(project_with_configs)
    assert result["run"]["scope"] == "full_app"
    assert result["project"]["status"] == "complete"
    assert result["plan"]["status"] == "complete"
    assert len(result["build"]["sections"]) == 2


def test_config_handles_all_config_files():
    assert set(CONFIG_FILES.keys()) == {"run", "project", "plan", "build", "compliance"}

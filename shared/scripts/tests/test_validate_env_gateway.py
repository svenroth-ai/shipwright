"""The gateway variables are discoverable from the scaffold (#547).

They were visible only in code, tests and planning artifacts, so an operator
could not find the feature without reading the source. They are scaffolded as
an ``alternative`` route: written into NEW files, never reported as missing,
never appended to an existing file.
"""

import json

import pytest

from shared.scripts.validate_env import init_env_file

_GATEWAY_VARS = [
    "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL",
    "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1",
    "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1",
    "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_2",
    "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_2",
]


@pytest.fixture
def project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "shipwright_run_config.json").write_text(json.dumps({"profile": "empty"}), encoding="utf-8")
    profiles = tmp_path / "p"
    profiles.mkdir()
    (profiles / "empty.json").write_text(json.dumps({
        "name": "empty", "required_env_vars": {"build": [], "deploy": [], "plugin": []},
    }), encoding="utf-8")
    return proj, profiles


@pytest.mark.covers("FR-01.13/AC07")
def test_new_env_file_lists_the_gateway_variables(project):
    proj, profiles = project
    result = init_env_file(proj, "all", profiles, include_framework=True)
    text = (proj / ".env.local").read_text(encoding="utf-8")

    assert result["action"] == "created"
    for name in _GATEWAY_VARS:
        assert f"# {name}=" in text
    assert "SHIPWRIGHT_REVIEW_GATEWAY_HEADER_<NAME>" in text  # the open-ended one is described


@pytest.mark.covers("FR-01.13/AC07")
def test_gateway_variables_are_never_reported_as_missing_keys(project):
    proj, profiles = project
    result = init_env_file(proj, "all", profiles, include_framework=True)

    assert set(result["missing_keys"]) == {"OPENROUTER_API_KEY", "OPENAI_API_KEY"}
    assert result["framework_keys"] == ["OPENROUTER_API_KEY", "OPENAI_API_KEY"]


@pytest.mark.covers("FR-01.13/AC07")
def test_existing_env_file_is_not_touched_for_the_gateway(project):
    proj, profiles = project
    env = proj / ".env.local"
    env.write_text("OPENROUTER_API_KEY=sk-or-real\nOPENAI_API_KEY=sk-real\n", encoding="utf-8")
    before = env.read_text(encoding="utf-8")

    result = init_env_file(proj, "all", profiles, include_framework=True)

    assert result["action"] == "unchanged"
    assert env.read_text(encoding="utf-8") == before


@pytest.mark.covers("FR-01.13/AC07")
def test_a_chosen_gateway_makes_the_two_keys_irrelevant(project):
    """A gateway-only operator must not be told to supply keys they never need."""
    proj, profiles = project
    (proj / ".env.local").write_text(
        "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL=https://gateway.example.com/v1\n", encoding="utf-8")

    result = init_env_file(proj, "all", profiles, include_framework=True)

    assert result["missing_keys"] == []


@pytest.mark.covers("FR-01.13/AC07")
def test_no_env_file_yet_never_lists_gateway_vars_as_missing(project):
    from shared.scripts.validate_env import _compute_missing_keys, _SHIPWRIGHT_FRAMEWORK_VARS

    proj, _ = project
    assert _compute_missing_keys(proj / ".env.local", _SHIPWRIGHT_FRAMEWORK_VARS) == [
        "OPENROUTER_API_KEY", "OPENAI_API_KEY"]

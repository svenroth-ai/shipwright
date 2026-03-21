"""Tests for shipwright-build sections module."""

from lib.sections import (
    extract_section_name,
    get_section_scope,
    is_valid_section_name,
    load_section_states,
)


def test_is_valid_section_name():
    assert is_valid_section_name("01-auth")
    assert is_valid_section_name("12-user-dashboard")
    assert not is_valid_section_name("auth")
    assert not is_valid_section_name("1-auth")
    assert not is_valid_section_name("01_auth")


def test_extract_section_name():
    assert extract_section_name("sections/01-auth.md") == "01-auth"
    assert extract_section_name("path/to/03-api.md") == "03-api"
    assert extract_section_name("invalid.md") is None


def test_get_section_scope():
    assert get_section_scope("01-auth") == "auth"
    assert get_section_scope("03-user-dashboard") == "user-dashboard"


def test_load_section_states(tmp_project_with_config):
    states = load_section_states(tmp_project_with_config)
    assert "01-auth" in states
    assert states["01-auth"]["status"] == "not_started"


def test_load_section_states_empty(tmp_path):
    states = load_section_states(tmp_path)
    assert states == {}

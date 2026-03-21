"""Tests for shipwright-project state detection."""

from lib.state import detect_state, is_valid_split_dir


def test_is_valid_split_dir():
    assert is_valid_split_dir("01-auth")
    assert is_valid_split_dir("02-user-management")
    assert is_valid_split_dir("12-multi-word-name")
    assert not is_valid_split_dir("auth")
    assert not is_valid_split_dir("1-auth")  # single digit
    assert not is_valid_split_dir("01_auth")  # underscore
    assert not is_valid_split_dir("01-Auth")  # uppercase


def test_detect_state_empty(tmp_planning):
    state = detect_state(tmp_planning)
    assert state["resume_step"] == 1
    assert not state["interview_complete"]
    assert not state["manifest_created"]
    assert not state["directories_created"]


def test_detect_state_after_interview(planning_with_interview):
    state = detect_state(planning_with_interview)
    assert state["resume_step"] == 2
    assert state["interview_complete"]
    assert not state["manifest_created"]


def test_detect_state_after_manifest(planning_with_manifest):
    state = detect_state(planning_with_manifest)
    assert state["resume_step"] == 4
    assert state["interview_complete"]
    assert state["manifest_created"]
    assert not state["directories_created"]


def test_detect_state_after_dirs(planning_with_dirs):
    state = detect_state(planning_with_dirs)
    assert state["resume_step"] == 6
    assert state["directories_created"]
    assert state["splits"] == ["01-auth", "02-dashboard"]
    assert state["splits_with_specs"] == []


def test_detect_state_after_specs(planning_with_specs):
    state = detect_state(planning_with_specs)
    assert state["resume_step"] == 7
    assert state["splits_with_specs"] == ["01-auth", "02-dashboard"]

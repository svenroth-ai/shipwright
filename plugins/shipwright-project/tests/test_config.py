"""Tests for shipwright-project config module."""

from lib.config import (
    SessionFilename,
    check_input_file_changed,
    compute_file_hash,
    create_initial_session_state,
    load_session_state,
    save_session_state,
    session_state_exists,
)


def test_session_filenames_use_shipwright_prefix():
    assert "shipwright" in SessionFilename.STATE
    assert "shipwright" in SessionFilename.INTERVIEW
    assert "deep" not in SessionFilename.STATE
    assert "deep" not in SessionFilename.INTERVIEW


def test_compute_file_hash(sample_requirements):
    hash1 = compute_file_hash(sample_requirements)
    assert hash1.startswith("sha256:")
    assert len(hash1) > 10

    # Same file → same hash
    hash2 = compute_file_hash(sample_requirements)
    assert hash1 == hash2


def test_compute_file_hash_changes(sample_requirements):
    hash1 = compute_file_hash(sample_requirements)
    sample_requirements.write_text("Changed content")
    hash2 = compute_file_hash(sample_requirements)
    assert hash1 != hash2


def test_session_state_roundtrip(tmp_planning):
    assert not session_state_exists(tmp_planning)

    state = {"input_file_hash": "sha256:abc", "session_created_at": "2026-03-21T00:00:00Z"}
    save_session_state(tmp_planning, state)

    assert session_state_exists(tmp_planning)

    loaded = load_session_state(tmp_planning)
    assert loaded == state


def test_create_initial_session_state(sample_requirements):
    state = create_initial_session_state(sample_requirements)
    assert "input_file_hash" in state
    assert "session_created_at" in state
    assert state["input_file_hash"].startswith("sha256:")


def test_check_input_file_changed_no_state(tmp_planning, sample_requirements):
    result = check_input_file_changed(tmp_planning, sample_requirements)
    assert result is None


def test_check_input_file_unchanged(tmp_planning, sample_requirements):
    state = create_initial_session_state(sample_requirements)
    save_session_state(tmp_planning, state)

    assert check_input_file_changed(tmp_planning, sample_requirements) is False


def test_check_input_file_changed(tmp_planning, sample_requirements):
    state = create_initial_session_state(sample_requirements)
    save_session_state(tmp_planning, state)

    sample_requirements.write_text("Changed!")
    assert check_input_file_changed(tmp_planning, sample_requirements) is True

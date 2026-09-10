"""Tests for ``completed_phases`` — the single shared implementation of the
phase_tasks[]-only progress rule (campaign p4-04-retire-write-once-steps).

Introduced in sub-iterate s4 as ``completed_phases_with_fallback`` (a
phase_tasks[]-first / completed_steps-fallback rule; external review, GLM +
OpenAI, independently: three call sites re-deriving this rule risk drifting,
so it lives here once). Sub-iterate s5 retired the write-once
``current_step``/``completed_steps`` fields and every writer of them — the v1
``update_step`` path now advances ``phase_tasks[]`` directly, so there is no
other source left to fall back to, and this module was renamed to
``completed_phases`` to say so. This file replaces
``test_handoff_phase_status_fallback.py``, whose tests pinned the now-removed
fallback branch itself.
"""

from __future__ import annotations

from lib.handoff_phase_status import completed_phases


def test_empty_when_phase_tasks_absent():
    # A v1-only / standalone config with no phase_tasks[] key at all has no
    # phase_tasks[]-derived evidence — and, since s5, nothing else to read.
    assert completed_phases({}) == set()


def test_computed_from_phase_tasks_when_present_and_usable():
    run_config = {
        "phase_tasks": [
            {"phase": "project", "status": "done"},
            {"phase": "design", "status": "done"},
            {"phase": "build", "status": "skipped"},
        ],
    }
    assert completed_phases(run_config) == {"project", "design", "build"}


def test_empty_set_is_trusted_when_phase_tasks_is_present_mid_flight():
    # A driven run mid-flight has phase_tasks[] PRESENT (not absent) with
    # nothing terminal yet. That empty completed set is itself the
    # authoritative answer.
    run_config = {"phase_tasks": [{"phase": "project", "status": "in_progress"}]}
    assert completed_phases(run_config) == set()


def test_empty_when_phase_tasks_is_a_bare_empty_list():
    # Doubt review, sub-iterate s4: a bare empty list has no entries to be
    # confident ABOUT.
    assert completed_phases({"phase_tasks": []}) == set()


def test_empty_when_phase_tasks_is_malformed():
    # phase_tasks present but not a list at all (corrupted config).
    assert completed_phases({"phase_tasks": "not-a-list"}) == set()


def test_empty_when_phase_tasks_is_a_non_empty_list_with_no_usable_entries():
    # External Tier-3 review, sub-iterate s4: a non-empty list containing
    # only entries that are not dicts, or dicts with no string `phase`, is
    # truthy (so the bare-empty-list check above does not catch it) but has
    # nothing for phase_tasks_progress to read.
    run_config = {"phase_tasks": [{}, "not-a-task"]}
    assert completed_phases(run_config) == set()


def test_empty_when_phase_task_entry_has_no_status():
    # A dict entry with a valid string `phase` but no `status` key at all is
    # unclassifiable — status_of() returns None, not "not finished".
    run_config = {"phase_tasks": [{"phase": "design"}]}
    assert completed_phases(run_config) == set()


def test_empty_when_phase_task_entry_has_a_malformed_status():
    run_config = {"phase_tasks": [{"phase": "design", "status": "???"}]}
    assert completed_phases(run_config) == set()


def test_empty_when_phase_tasks_mixes_valid_and_malformed_entries():
    # External Tier-3 review, sub-iterate s4 (fourth pass): phase_tasks_has
    # _usable_entries requires ALL entries to be usable, not just one — a
    # list with one valid entry alongside a malformed one is untrusted
    # wholesale, not partially trusted.
    run_config = {
        "phase_tasks": [
            {"phase": "project", "status": "done"},
            {"phase": "design"},
        ],
    }
    assert completed_phases(run_config) == set()


def test_folds_skipped_into_completed_same_as_done():
    run_config = {"phase_tasks": [{"phase": "test", "status": "skipped"}]}
    assert completed_phases(run_config) == {"test"}


def test_completed_steps_is_never_consulted():
    # s5: the write-once completed_steps field is retired — even a config
    # that still carries it (a leftover from before this campaign) must not
    # have it read, whether phase_tasks[] agrees, disagrees, or is absent.
    run_config = {"completed_steps": ["project", "design"]}
    assert completed_phases(run_config) == set()

    run_config_with_tasks = {
        "completed_steps": ["project", "design"],
        "phase_tasks": [{"phase": "project", "status": "in_progress"}],
    }
    assert completed_phases(run_config_with_tasks) == set()

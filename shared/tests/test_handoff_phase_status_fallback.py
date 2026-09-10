"""Tests for ``completed_phases_with_fallback`` — the single shared
implementation of the phase_tasks[]-first / completed_steps-fallback rule
(campaign p4-04-retire-write-once-steps, sub-iterate s4; external review,
GLM + OpenAI, independently: three call sites re-deriving this rule risk
drifting, so it lives here once).
"""

from __future__ import annotations

from lib.handoff_phase_status import completed_phases_with_fallback


def test_falls_back_to_completed_steps_when_phase_tasks_absent():
    # Standalone/v1-only config — no phase_tasks[] key at all.
    run_config = {"completed_steps": ["project", "plan"]}
    assert completed_phases_with_fallback(run_config) == {"project", "plan"}


def test_prefers_phase_tasks_over_stale_completed_steps():
    run_config = {
        "completed_steps": ["project"],
        "phase_tasks": [
            {"phase": "project", "status": "done"},
            {"phase": "design", "status": "done"},
            {"phase": "build", "status": "skipped"},
        ],
    }
    assert completed_phases_with_fallback(run_config) == {"project", "design", "build"}


def test_empty_when_neither_source_present():
    assert completed_phases_with_fallback({}) == set()


def test_trusts_an_empty_completed_set_when_phase_tasks_is_present():
    # The high-severity finding from external review (this sub-iterate): a
    # driven run mid-flight has phase_tasks[] PRESENT (not absent) with
    # nothing terminal yet. That empty completed set is itself the
    # authoritative answer — completed_steps (here stale/wrong, claiming
    # "design" done) must NOT be consulted just because nothing has
    # finished YET.
    run_config = {
        "completed_steps": ["project", "design"],
        "phase_tasks": [{"phase": "project", "status": "in_progress"}],
    }
    assert completed_phases_with_fallback(run_config) == set()


def test_falls_back_when_phase_tasks_is_a_bare_empty_list():
    # Doubt review, sub-iterate s4: a bare empty list has no entries to be
    # confident ABOUT — distinct from the mid-flight case above (>=1 entry,
    # nothing finished YET), which is why the fallback trigger checks for
    # entries and not merely list-ness. This also matches
    # phase_tasks_progress()'s own "no confident evidence at all" threshold
    # for its four callers (state.py, the two hooks, sub-iterate s3) — a
    # driven run is never a bare empty list (config_factory always seeds
    # >=1 task from creation), so this shape only arises from a hand-edited
    # or degenerate config, same as the "absent" and "malformed" cases.
    run_config = {"completed_steps": ["project"], "phase_tasks": []}
    assert completed_phases_with_fallback(run_config) == {"project"}


def test_falls_back_when_phase_tasks_is_malformed():
    # phase_tasks present but not a list at all (corrupted config) is
    # indistinguishable from absent for this rule's purposes.
    run_config = {"completed_steps": ["project"], "phase_tasks": "not-a-list"}
    assert completed_phases_with_fallback(run_config) == {"project"}


def test_falls_back_when_phase_tasks_is_a_non_empty_list_with_no_usable_entries():
    # External Tier-3 review, sub-iterate s4: a non-empty list containing
    # only entries that are not dicts, or dicts with no string `phase`, is
    # truthy (so the bare-empty-list check above does not catch it) but has
    # nothing for phase_tasks_progress to read — that call would return an
    # empty completed set, indistinguishable from a genuine mid-flight run
    # with nothing finished yet. Trusting it would silently under-report
    # already-completed phases a stale completed_steps still remembers.
    run_config = {"completed_steps": ["project"], "phase_tasks": [{}, "not-a-task"]}
    assert completed_phases_with_fallback(run_config) == {"project"}


def test_falls_back_when_phase_task_entry_has_no_status():
    # External Tier-3 review, sub-iterate s4 (second pass): a dict entry
    # with a valid string `phase` but no `status` key at all has a phase
    # name but nothing phase_tasks_progress can classify — status_of()
    # returns None, which is not "not finished", it is "unknown". Trusting
    # this as confident evidence would silently ignore completed_steps's
    # valid, non-stale claim that "design" is already done.
    run_config = {"completed_steps": ["design"], "phase_tasks": [{"phase": "design"}]}
    assert completed_phases_with_fallback(run_config) == {"design"}


def test_falls_back_when_phase_task_entry_has_a_malformed_status():
    # Same as above, but the status key is present with an unrecognized
    # value rather than absent — equally unclassifiable, so equally not
    # "usable evidence" for this predicate's purposes.
    run_config = {
        "completed_steps": ["design"],
        "phase_tasks": [{"phase": "design", "status": "???"}],
    }
    assert completed_phases_with_fallback(run_config) == {"design"}


def test_falls_back_when_phase_tasks_mixes_valid_and_malformed_entries():
    # External Tier-3 review, sub-iterate s4 (fourth pass): phase_tasks_has
    # _usable_entries used any(), so a list with ONE valid entry alongside
    # a malformed one (no status) was trusted wholesale — phase_tasks_
    # progress then silently drops the malformed phase from `completed`
    # instead of the whole function falling back to completed_steps for it.
    # Requiring ALL entries to be usable (not just one) closes this: the
    # entire list is untrusted when even one entry is unreadable, so a
    # stale-but-valid completed_steps for the unreadable phase is not lost.
    run_config = {
        "completed_steps": ["project", "design"],
        "phase_tasks": [
            {"phase": "project", "status": "done"},
            {"phase": "design"},
        ],
    }
    assert completed_phases_with_fallback(run_config) == {"project", "design"}


def test_completed_steps_fallback_skips_unhashable_entries():
    # External code review (this sub-iterate, OpenAI): a legacy/hand-edited
    # completed_steps list can carry a non-string (dict/list) entry — old
    # configs never validated this list. A bare `set(steps)` would raise
    # TypeError (unhashable type) building the fallback set; the malformed
    # entry must be skipped instead, same as every other reader of this list
    # (mirrors adopted_phase_tasks.backfill_missing_phase_tasks's guard).
    run_config = {"completed_steps": [{"phase": "project"}, "design", ["build"]]}
    assert completed_phases_with_fallback(run_config) == {"design"}


def test_folds_skipped_into_completed_same_as_done():
    # Matches what completed_steps itself already did pre-migration
    # (config_factory lists a standalone-skipped phase, e.g. a no-CI "test",
    # in completed_steps exactly like one that actually ran).
    run_config = {"phase_tasks": [{"phase": "test", "status": "skipped"}]}
    assert completed_phases_with_fallback(run_config) == {"test"}

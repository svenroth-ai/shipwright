"""Phase-Quality reads the v2 ``phase_tasks[]`` authority — the SOLE one.

``current_step`` / ``completed_steps`` were **write-once** in a driven run:
``config_factory`` stamped them at run creation and the v2 lifecycle
(``phase_task_lifecycle``) never advanced them — only the v1 ``update_step``
path did, and that path is inert on a driven run
(``test_update_step_driven_run_guard``). Two Phase-Quality readers used to key
on them too:

* :func:`phase_is_engaged` — which phases the Stop-time audit covers;
* :func:`resolve_source` — the orchestrator / standalone audit-source stamp.

Campaign p4-04-retire-write-once-steps, sub-iterate s5 retired both fields
and every writer of them: the v1 ``update_step`` path now advances
``phase_tasks[]`` directly, so it is always the complete picture and there is
nothing left to union with. A config that still carries the old fields (a
leftover from before this campaign) has them read by neither function any
more — this file's earlier "Union, not replacement" contract is retired
along with the fields it unioned.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.phase_quality as pq  # noqa: E402
from lib.handoff_phase_status import KNOWN_STATUSES  # noqa: E402
from lib.phase_quality._engagement import (  # noqa: E402
    ENGAGED_TASK_STATUSES,
    _STATUS_ENGAGES,
)


def _task(phase: str, status: str) -> dict:
    return {"phaseTaskId": f"pt-{phase}", "phase": phase, "status": status}


def _v2_cfg(*tasks: dict, status: str = "in_progress") -> dict:
    """A driven v2 config: phase_tasks[] is the sole authority."""
    return {
        "schemaVersion": 2,
        "mode": "single_session",
        "status": status,
        "phase_tasks": list(tasks),
    }


# --- phase_is_engaged: the v2 authority ----------------------------------

@pytest.mark.parametrize("task_status", ["in_progress", "done", "failed"])
def test_v2_phase_task_that_ran_is_engaged(task_status: str) -> None:
    cfg = _v2_cfg(_task("project", "done"), _task("build", task_status))
    assert pq.phase_is_engaged("build", cfg, []) is True


@pytest.mark.parametrize("task_status", ["backlog", "awaiting_launch", "skipped"])
def test_v2_phase_task_that_did_not_run_is_not_engaged(task_status: str) -> None:
    """Planned-but-never-started grants nothing. `skipped` is here too: with no
    other evidence it means the phase never executed — including the
    standalone-completed case, since s5 retired the completed_steps read
    that used to distinguish it (see
    ``test_skipped_task_with_stale_completed_steps_is_not_engaged`` below)."""
    cfg = _v2_cfg(_task("project", "done"), _task("deploy", task_status))
    assert pq.phase_is_engaged("deploy", cfg, []) is False


def test_v2_unlisted_phase_is_not_engaged() -> None:
    cfg = _v2_cfg(_task("project", "done"))
    assert pq.phase_is_engaged("deploy", cfg, []) is False


def test_v2_complete_run_does_not_re_admit_a_phase() -> None:
    """AC-2 holds for v2 too: a finished run is iterate-only, so a done
    phase_task must not re-admit its phase."""
    cfg = _v2_cfg(_task("build", "done"), status="complete")
    assert pq.phase_is_engaged("build", cfg, []) is False


def test_v2_complete_run_still_engages_iterate() -> None:
    cfg = _v2_cfg(_task("build", "done"), status="complete")
    assert pq.phase_is_engaged("iterate", cfg, []) is True


# --- s5: the retired v1 fields grant nothing, even when still present -----

def test_skipped_task_with_stale_completed_steps_is_not_engaged() -> None:
    """Before s5, config_factory marking a standalone-completed phase
    `skipped` in phase_tasks[] while also recording it in completed_steps
    meant the union still engaged it. completed_steps is retired and no
    longer read, so a bare `skipped` status (with nothing else showing the
    phase ran) is not engaged — even though the leftover field still claims
    it completed."""
    cfg = _v2_cfg(_task("project", "skipped"))
    cfg["completed_steps"] = ["project"]  # leftover write-once field, ignored
    assert pq.phase_is_engaged("project", cfg, []) is False


def test_stale_current_step_grants_no_engagement() -> None:
    """A leftover current_step naming a phase with no phase_tasks[] entry at
    all used to still engage it via the v1 union; s5 retired that read."""
    cfg = _v2_cfg(_task("project", "done"))
    cfg["current_step"] = "plan"  # leftover write-once field, ignored
    assert pq.phase_is_engaged("plan", cfg, []) is False


@pytest.mark.parametrize("bad", [None, {}, "phase_tasks", [None], [1, 2]])
def test_malformed_phase_tasks_is_not_engaged_despite_stale_completed_steps(
    bad: object,
) -> None:
    """A malformed v2 array must not raise, and — since s5 — must not fall
    back to a stale completed_steps either: there is no other source left to
    read, so this is simply not engaged."""
    cfg = {"status": "in_progress", "completed_steps": ["plan"], "phase_tasks": bad}
    assert pq.phase_is_engaged("plan", cfg, []) is False


def test_malformed_phase_tasks_without_v1_evidence_is_not_engaged() -> None:
    cfg = {"status": "in_progress", "phase_tasks": [None]}
    assert pq.phase_is_engaged("build", cfg, []) is False


def test_non_dict_task_entries_are_skipped_not_fatal() -> None:
    cfg = _v2_cfg()
    cfg["phase_tasks"] = [None, "x", _task("build", "done")]
    assert pq.phase_is_engaged("build", cfg, []) is True


@pytest.mark.parametrize("bad_status", [["done"], {"s": "done"}, 7, None])
def test_unhashable_or_non_string_status_does_not_raise(bad_status: object) -> None:
    """``x in frozenset`` HASHES x, so a list/dict status raises TypeError on a raw
    read. That would escape into the Stop hook's outer except and silently skip the
    backlog emit — so the status is read through ``status_of``."""
    cfg = _v2_cfg({"phase": "build", "status": bad_status})
    assert pq.phase_is_engaged("build", cfg, []) is False


def test_unhashable_status_does_not_get_rescued_by_stale_completed_steps() -> None:
    cfg = _v2_cfg({"phase": "build", "status": ["done"]})
    cfg["completed_steps"] = ["build"]  # leftover write-once field, ignored
    assert pq.phase_is_engaged("build", cfg, []) is False


# --- drift guard on the status vocabulary ---------------------------------

def test_every_known_status_is_classified() -> None:
    """Adding a status to the v2 schema must mean CLASSIFYING it for engagement.

    Without this, an unclassified newcomer silently reads as not-engaged: its
    Tier-1 FAILs get rewritten to SKIP and the audit covers FEWER phases — the one
    direction this module forbids. ``KNOWN_STATUSES`` is itself pinned to
    ``run_config.v2.schema.json`` by ``test_handoff_pipeline_pointer``.
    """
    assert set(_STATUS_ENGAGES) == set(KNOWN_STATUSES)


@pytest.mark.parametrize("forced", ["awaiting_launch", "skipped"])
def test_task_recovered_to_a_not_started_status_is_still_engaged(forced: str) -> None:
    """`recover_phase_task` can force a task that RAN back to `awaiting_launch`,
    or retire it as `skipped`. It nulls `startedAt` but deliberately preserves
    `executionCount`, so execution history is what keeps the phase audited — the
    retired `completed_steps` field never could."""
    task = _task("build", forced)
    task["executionCount"] = 1
    assert pq.phase_is_engaged("build", _v2_cfg(task), []) is True


@pytest.mark.parametrize("count", [0, None, "1", True, [1]])
def test_never_run_task_is_not_engaged_and_bad_counts_do_not_raise(count: object) -> None:
    """A fresh task has executionCount 0; a malformed one must not raise inside a
    Stop hook. `True` is excluded on purpose — bool is an int subclass."""
    task = _task("deploy", "awaiting_launch")
    task["executionCount"] = count
    assert pq.phase_is_engaged("deploy", _v2_cfg(task), []) is False


@pytest.mark.parametrize("run_status", ["needs_validation", "failed"])
def test_unfinished_run_still_audits_every_phase_that_ran(run_status: str) -> None:
    """Only `complete` closes a run. A run parked in needs_validation or failed
    has NOT finished, so phases that ran stay audited — the audit-MORE direction,
    and exactly the runs where an open Tier-1 FAIL matters most."""
    cfg = _v2_cfg(_task("build", "done"), status=run_status)
    assert pq.phase_is_engaged("build", cfg, []) is True


def test_v2_only_config_engages_without_any_v1_field() -> None:
    """s5: current_step / completed_steps are dropped for real now —
    phase_tasks[] alone answers, exactly as this guard (written ahead of the
    retirement, trg-8d52a965) anticipated. If it did not, resolve_engaged_phases'
    `engaged or all_phases` fail-open would mask it as a silent widening to all
    11 phases instead of a visible failure."""
    cfg = {"schemaVersion": 2, "status": "in_progress",
           "phase_tasks": [_task("project", "done"), _task("build", "in_progress")]}
    assert pq.phase_is_engaged("project", cfg, []) is True
    assert pq.phase_is_engaged("build", cfg, []) is True
    assert pq.phase_is_engaged("deploy", cfg, []) is False


def test_engaged_statuses_are_exactly_the_three_that_ran() -> None:
    """Pins the VERDICTS, not just the vocabulary.

    Written out literally rather than re-deriving from ``_STATUS_ENGAGES`` — a
    comprehension copied from the module is a tautology that stays green when a
    classification is flipped. This catches both a broken derivation and a
    changed decision, and `skipped` is the one most likely to be argued.
    """
    assert ENGAGED_TASK_STATUSES == frozenset({"in_progress", "done", "failed"})


# resolve_source / has_phase_tasks tests live in
# test_phase_quality_resolve_source.py — split out to keep this file under
# its 300-line bloat ceiling (campaign p4-04-retire-write-once-steps s2).

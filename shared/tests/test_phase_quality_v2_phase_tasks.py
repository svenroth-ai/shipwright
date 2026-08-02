"""Phase-Quality reads the v2 ``phase_tasks[]`` authority, not the frozen v1 fields.

``current_step`` / ``completed_steps`` are **write-once** in a driven run:
``config_factory`` stamps them at run creation and the v2 lifecycle
(``phase_task_lifecycle``) never advances them — only the v1 ``update_step``
path does, and that path is inert on a driven run (``test_update_step_driven_run_guard``).
Two Phase-Quality readers still keyed on them:

* :func:`phase_is_engaged` — which phases the Stop-time audit covers;
* :func:`resolve_source` — the orchestrator / standalone audit-source stamp.

On a v2 run both therefore answered from state frozen at ``"project"``.

**Union, not replacement.** v2 ``phase_tasks[]`` is consulted *in addition to*
the v1 fields, never instead of them. The v1 shape is still actively written
(``shipwright-project``, ``shipwright-adopt``, and the v1 ``update_step`` path),
and ``config_factory`` marks a standalone-completed phase ``skipped`` in
``phase_tasks[]`` while recording it in ``completed_steps`` — so a v2-only read
would drop engagement the v1 read grants. This module's contract is
"audit MORE, never silently fewer", so the two sources are OR-ed.
"""

from __future__ import annotations

import json
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
    """A driven v2 config: phase_tasks[] live, v1 fields FROZEN at creation."""
    return {
        "schemaVersion": 2,
        "mode": "single_session",
        "status": status,
        # Write-once: stamped by config_factory, never advanced afterwards.
        "current_step": "project",
        "completed_steps": [],
        "phase_tasks": list(tasks),
    }


# --- phase_is_engaged: the v2 authority ----------------------------------

@pytest.mark.parametrize("task_status", ["in_progress", "done", "failed"])
def test_v2_phase_task_that_ran_is_engaged(task_status: str) -> None:
    """A phase that ran (or is running) is engaged even though current_step
    still says "project" — the regression this migration fixes."""
    cfg = _v2_cfg(_task("project", "done"), _task("build", task_status))
    assert pq.phase_is_engaged("build", cfg, []) is True


@pytest.mark.parametrize("task_status", ["backlog", "awaiting_launch", "skipped"])
def test_v2_phase_task_that_did_not_run_is_not_engaged(task_status: str) -> None:
    """Planned-but-never-started grants nothing — mirroring v1, where a future
    pipeline step was in neither completed_steps nor current_step. `skipped` is
    here too: with NO v1 evidence it means the phase never executed (the
    already-done-standalone case is covered by completed_steps, tested below)."""
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


# --- union: v2 must never subtract what v1 granted ------------------------

def test_skipped_task_still_engaged_via_v1_completed_steps() -> None:
    """config_factory marks a phase completed STANDALONE as ``skipped`` in
    phase_tasks[] while carrying it in completed_steps. ``skipped`` alone does
    not mean "ran", so only the union keeps this phase audited."""
    cfg = _v2_cfg(_task("project", "skipped"))
    cfg["completed_steps"] = ["project"]
    assert pq.phase_is_engaged("project", cfg, []) is True


def test_v1_current_step_still_engaged_alongside_phase_tasks() -> None:
    cfg = _v2_cfg(_task("project", "done"))
    cfg["current_step"] = "plan"
    assert pq.phase_is_engaged("plan", cfg, []) is True


@pytest.mark.parametrize("bad", [None, {}, "phase_tasks", [None], [1, 2]])
def test_malformed_phase_tasks_falls_back_to_v1(bad: object) -> None:
    """A malformed v2 array must not raise and must not suppress the v1 read."""
    cfg = {"status": "in_progress", "completed_steps": ["plan"], "phase_tasks": bad}
    assert pq.phase_is_engaged("plan", cfg, []) is True


def test_malformed_phase_tasks_without_v1_evidence_is_not_engaged() -> None:
    cfg = {"status": "in_progress", "completed_steps": [], "phase_tasks": [None]}
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


def test_unhashable_status_does_not_suppress_the_v1_read() -> None:
    cfg = _v2_cfg({"phase": "build", "status": ["done"]})
    cfg["completed_steps"] = ["build"]
    assert pq.phase_is_engaged("build", cfg, []) is True


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
    `executionCount`, so execution history is what keeps the phase audited — on a
    driven run the frozen `completed_steps` cannot."""
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
    """Guards the successor campaign (trg-8d52a965): once current_step /
    completed_steps are dropped, phase_tasks[] alone must still answer. If it did
    not, resolve_engaged_phases' `engaged or all_phases` fail-open would mask it
    as a silent widening to all 11 phases instead of a visible failure."""
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


# --- resolve_source: the audit-source stamp -------------------------------

def _write_cfg(project: Path, cfg: dict) -> None:
    (project / "shipwright_run_config.json").write_text(
        json.dumps(cfg), encoding="utf-8")


def test_resolve_source_v2_is_orchestrator_without_current_step(tmp_path: Path) -> None:
    """A driven run whose pipeline was fully pre-completed has current_step
    None, so the v1 read called it standalone. phase_tasks[] says otherwise."""
    cfg = _v2_cfg(_task("project", "done"), status="complete")
    cfg["current_step"] = None
    _write_cfg(tmp_path, cfg)
    assert pq.resolve_source(tmp_path, "build") == "orchestrator"


def test_resolve_source_v1_current_step_still_orchestrator(tmp_path: Path) -> None:
    _write_cfg(tmp_path, {"status": "in_progress", "current_step": "build"})
    assert pq.resolve_source(tmp_path, "build") == "orchestrator"


def test_resolve_source_explicit_standalone_flag_wins(tmp_path: Path) -> None:
    """An explicit standalone marker outranks phase_tasks[]."""
    cfg = _v2_cfg(_task("project", "done"))
    cfg["standalone"] = True
    _write_cfg(tmp_path, cfg)
    assert pq.resolve_source(tmp_path, "build") == "standalone"


def test_resolve_source_no_pipeline_evidence_is_standalone(tmp_path: Path) -> None:
    _write_cfg(tmp_path, {"status": "complete", "phase_tasks": [], "current_step": None})
    assert pq.resolve_source(tmp_path, "build") == "standalone"


def test_resolve_source_missing_config_is_standalone(tmp_path: Path) -> None:
    assert pq.resolve_source(tmp_path, "build") == "standalone"


def test_resolve_source_unreadable_config_is_standalone(tmp_path: Path) -> None:
    (tmp_path / "shipwright_run_config.json").write_text("{not json", encoding="utf-8")
    assert pq.resolve_source(tmp_path, "build") == "standalone"


def test_resolve_source_iterate_short_circuits(tmp_path: Path) -> None:
    _write_cfg(tmp_path, _v2_cfg(_task("project", "done")))
    assert pq.resolve_source(tmp_path, "iterate") == "iterate"


def test_resolve_source_malformed_phase_tasks_does_not_raise(tmp_path: Path) -> None:
    _write_cfg(tmp_path, {"status": "in_progress", "phase_tasks": {"a": 1}})
    assert pq.resolve_source(tmp_path, "build") == "standalone"


@pytest.mark.parametrize("body", ["[1, 2]", "null", '"a string"', "7"])
def test_resolve_source_non_dict_config_is_standalone(tmp_path: Path, body: str) -> None:
    """Valid JSON that is not an object used to reach ``data.get`` and raise
    AttributeError."""
    (tmp_path / "shipwright_run_config.json").write_text(body, encoding="utf-8")
    assert pq.resolve_source(tmp_path, "build") == "standalone"


@pytest.mark.parametrize("body", ["[1, 2]", "null", '"a string"', "7"])
def test_resolve_run_id_survives_a_non_dict_config(tmp_path: Path, body: str) -> None:
    """The Stop hook calls resolve_run_id FIRST, outside its per-phase try and
    AFTER the once-per-Stop claim is taken. A raise here killed the audit for
    EVERY phase and left the sibling plugin invocations no-oping on the burned
    claim — so resolve_source's own guard was never even reached."""
    (tmp_path / "shipwright_run_config.json").write_text(body, encoding="utf-8")
    assert pq.resolve_run_id(tmp_path, "session-abc") == "session-abc"


def test_engagement_reads_two_events_sharing_one_physical_line(tmp_path: Path) -> None:
    """A merge=union merge can leave two records on one line. A per-line
    json.loads drops BOTH — here that would un-engage a phase whose
    phase_completed event was its only evidence, i.e. audit FEWER."""
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8")
    a = json.dumps({"type": "phase_completed", "source": "design"})
    b = json.dumps({"type": "phase_completed", "source": "deploy"})
    (tmp_path / "shipwright_events.jsonl").write_text(a + b + "\n", encoding="utf-8")
    _cfg, events = pq.load_engagement_inputs(tmp_path)
    assert pq.phase_is_engaged("design", _cfg, events) is True
    assert pq.phase_is_engaged("deploy", _cfg, events) is True

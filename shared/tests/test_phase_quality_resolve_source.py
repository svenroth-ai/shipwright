"""Phase-Quality's ``resolve_source`` — the orchestrator / standalone / iterate
audit-source stamp — and the ``has_phase_tasks`` primitive it and
``phase_is_engaged`` both key on.

Split out of test_phase_quality_v2_phase_tasks.py (campaign
p4-04-retire-write-once-steps s2, bloat gate: the shared file crossed its
300-line limit) — a cohesive, single-purpose group already delimited by that
file's own "resolve_source: the audit-source stamp" section marker.
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
from lib.phase_quality._engagement import has_phase_tasks  # noqa: E402


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


def test_resolve_source_v1_current_step_alone_is_standalone(tmp_path: Path) -> None:
    """current_step, and every reader of it, is retired (sub-iterate s5): a
    config carrying only that leftover field — no phase_tasks[] — has no
    orchestrator-driven evidence left to read, so it classifies standalone."""
    _write_cfg(tmp_path, {"status": "in_progress", "current_step": "build"})
    assert pq.resolve_source(tmp_path, "build") == "standalone"


def test_resolve_source_explicit_standalone_flag_wins(tmp_path: Path) -> None:
    """An explicit standalone marker outranks phase_tasks[]."""
    cfg = _v2_cfg(_task("project", "done"))
    cfg["standalone"] = True
    _write_cfg(tmp_path, cfg)
    assert pq.resolve_source(tmp_path, "build") == "standalone"


def test_resolve_source_no_pipeline_evidence_is_standalone(tmp_path: Path) -> None:
    _write_cfg(tmp_path, {"status": "complete", "phase_tasks": [], "current_step": None})
    assert pq.resolve_source(tmp_path, "build") == "standalone"


def test_resolve_source_all_adopted_phase_tasks_is_still_standalone(tmp_path: Path) -> None:
    """shipwright-adopt (campaign p4-04-retire-write-once-steps s2) seeds
    phase_tasks[] entries marked establishedAtAdoption: true, alongside
    completed_steps, for a repo that was never orchestrator-driven. Those
    entries are not phase-task-lifecycle evidence, so an all-adopted array
    must not flip an adopted repo's source label to "orchestrator"."""
    cfg = {
        "status": "complete",
        "current_step": None,
        "completed_steps": ["project", "plan", "build", "test"],
        "phase_tasks": [
            {**_task("project", "done"), "establishedAtAdoption": True},
            {**_task("test", "skipped"), "establishedAtAdoption": True},
        ],
    }
    _write_cfg(tmp_path, cfg)
    assert pq.resolve_source(tmp_path, "build") == "standalone"


def test_has_phase_tasks_false_when_every_entry_is_adopted(tmp_path: Path) -> None:
    cfg = {
        "phase_tasks": [
            {**_task("project", "done"), "establishedAtAdoption": True},
        ],
    }
    assert has_phase_tasks(cfg) is False


def test_has_phase_tasks_true_when_a_real_task_sits_alongside_adopted_ones() -> None:
    cfg = {
        "phase_tasks": [
            {**_task("project", "done"), "establishedAtAdoption": True},
            _task("build", "in_progress"),
        ],
    }
    assert has_phase_tasks(cfg) is True


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

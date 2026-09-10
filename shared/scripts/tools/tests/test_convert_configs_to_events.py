"""Tests for convert_configs_to_events.py's phase-event source.

Campaign p4-04-retire-write-once-steps, sub-iterate s4: the one-time
config->events migration reads ``phase_tasks[]`` — see
``shared/scripts/lib/handoff_phase_status.py::completed_phases``, the single
shared implementation of this rule (external review, this sub-iterate: three
independent copies risk drifting). Sub-iterate s5 retired the write-once
``current_step``/``completed_steps`` fields and every writer of them: the v1
``update_step`` path now advances ``phase_tasks[]`` directly, so
``completed_phases`` no longer has anything to fall back to, and neither does
this tool.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools.convert_configs_to_events import convert


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_convert_emits_phase_completed_from_phase_tasks(tmp_path: Path):
    # End-to-end: convert() must emit phase_completed events for phases
    # phase_tasks[] reports finished, even when the retired completed_steps
    # field disagrees (a leftover from a config predating this campaign).
    _write_json(tmp_path / "shipwright_run_config.json", {
        "pipeline": ["project", "design", "plan", "build"],
        "completed_steps": ["project"],
        "phase_tasks": [
            {"phase": "project", "status": "done"},
            {"phase": "design", "status": "done"},
            {"phase": "plan", "status": "in_progress"},
        ],
        "updated_at": "2026-09-10T00:00:00Z",
    })
    events = convert(tmp_path)
    phase_completed = {e["phase"] for e in events if e["type"] == "phase_completed"}
    assert phase_completed == {"project", "design"}
    assert "plan" not in phase_completed
    assert "build" not in phase_completed


def test_convert_emits_nothing_for_a_config_with_no_phase_tasks(tmp_path: Path):
    # No phase_tasks[] at all (e.g. a standalone/v1-only config predating
    # phase_tasks[] seeding) — s5 retired the completed_steps fallback, so
    # there is nothing left to read and no phase_completed events emit.
    _write_json(tmp_path / "shipwright_run_config.json", {
        "pipeline": ["project", "design"],
        "completed_steps": ["project"],
        "updated_at": "2026-09-10T00:00:00Z",
    })
    events = convert(tmp_path)
    phase_completed = {e["phase"] for e in events if e["type"] == "phase_completed"}
    assert phase_completed == set()


def test_convert_trusts_empty_phase_tasks_over_the_retired_completed_steps(tmp_path: Path):
    # External review (GLM + OpenAI, independently): a driven run mid-flight
    # with phase_tasks[] PRESENT but nothing terminal yet (only "project"
    # materialized, still in_progress) reports nothing completed — that
    # emptiness is itself the authoritative answer, not a cue to consult the
    # retired completed_steps field (here claiming "design" is done).
    _write_json(tmp_path / "shipwright_run_config.json", {
        "pipeline": ["project", "design"],
        "completed_steps": ["project", "design"],
        "phase_tasks": [{"phase": "project", "status": "in_progress"}],
        "updated_at": "2026-09-10T00:00:00Z",
    })
    events = convert(tmp_path)
    phase_completed = {e["phase"] for e in events if e["type"] == "phase_completed"}
    assert phase_completed == set()


def test_convert_emits_phase_completed_for_a_skipped_phase(tmp_path: Path):
    # A phase_tasks[] entry terminalized as "skipped" (e.g. test skipped on
    # a no-CI project) counts as completed here — matching what
    # completed_steps itself already did pre-retirement (config_factory
    # listed a standalone-skipped phase in completed_steps exactly like one
    # that actually ran), so this migration tool keeps the same semantics.
    _write_json(tmp_path / "shipwright_run_config.json", {
        "pipeline": ["project", "test"],
        "phase_tasks": [
            {"phase": "project", "status": "done"},
            {"phase": "test", "status": "skipped"},
        ],
        "updated_at": "2026-09-10T00:00:00Z",
    })
    events = convert(tmp_path)
    phase_completed = {e["phase"] for e in events if e["type"] == "phase_completed"}
    assert phase_completed == {"project", "test"}

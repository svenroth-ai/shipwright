"""Which run id the gate's canon ``phase_history`` check verifies (A5 review, doubt high).

Real phase skills mint their own ``SHIPWRIGHT_RUN_ID``, and a phase-runner exports the run's
``runId``, so one id may label every split's and every claim's entry. The gate must accept
only an entry the phase recorded during ITS task. The real-skill round trip is
``integration-tests/test_phase_gate_real_skill_canon.py``.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator_pkg.gate_run_id import NO_ENTRY_SUFFIX, canon_run_id  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC02")

_CLAIM = datetime.now(timezone.utc) - timedelta(hours=1)
CLAIMED = _CLAIM.isoformat()
RUN = {"runId": "run-1a2b3c4d"}
NONE = "run-1a2b3c4d" + NO_ENTRY_SUFFIX


def _at(minutes: float) -> str:
    return (_CLAIM + timedelta(minutes=minutes)).isoformat()


def _history(root: Path, phase: str, *entries) -> None:
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": {phase: list(entries)}}), encoding="utf-8")


def _task(phase: str = "design", split: str | None = None, started: str | None = CLAIMED):
    return {"phase": phase, "splitId": split, "startedAt": started}


def test_the_runs_own_id_wins_when_recorded_during_the_task(tmp_path):
    _history(tmp_path, "design", {"run_id": "run-1a2b3c4d", "at": _at(1)},
             {"run_id": "design-1", "at": _at(2)})
    assert canon_run_id(tmp_path, _task(), RUN) == "run-1a2b3c4d"


def test_the_newest_entry_since_the_claim_is_the_phases_own(tmp_path):
    _history(tmp_path, "design", {"run_id": "design-a", "at": _at(1)},
             {"run_id": "design-b", "at": _at(2).replace("+00:00", "Z")})
    assert canon_run_id(tmp_path, _task(), RUN) == "design-b"


@pytest.mark.parametrize("run_id", ["design-old", "run-1a2b3c4d"])
def test_an_entry_from_before_the_claim_never_counts_even_under_the_runs_id(tmp_path, run_id):
    """A recovered task's first claim wrote this entry; the re-run must write its own."""
    _history(tmp_path, "design", {"run_id": run_id, "at": _at(-0.01)})
    assert canon_run_id(tmp_path, _task(), RUN) == NONE


def test_a_future_dated_entry_does_not_count(tmp_path):
    _history(tmp_path, "design", {"run_id": "run-1a2b3c4d", "at": _at(24 * 60)})
    assert canon_run_id(tmp_path, _task(), RUN) == NONE


def test_another_splits_entry_never_counts_even_under_the_runs_id(tmp_path):
    """plan/02 must not pass on plan/01's entry when both are labelled ``runId``."""
    _history(tmp_path, "plan", {"run_id": "run-1a2b3c4d", "at": _at(1), "split": "01-core"})
    assert canon_run_id(tmp_path, _task("plan", "02-ui"), RUN) == NONE


def test_a_split_task_takes_its_own_split_or_an_unsplit_entry(tmp_path):
    _history(tmp_path, "plan", {"run_id": "plan-01", "at": _at(1), "split": "01-core"},
             {"run_id": "plan-02", "at": _at(3), "split": "02-ui"})
    assert canon_run_id(tmp_path, _task("plan", "01-core"), RUN) == "plan-01"
    _history(tmp_path, "plan", {"run_id": "plan-x", "at": _at(1)})
    assert canon_run_id(tmp_path, _task("plan", "01-core"), RUN) == "plan-x"


@pytest.mark.parametrize("started", [None, "", "yesterday", "2026-10-25T10:00:00"])
def test_without_a_comparable_claim_time_the_runs_id_is_unchanged(tmp_path, started):
    _history(tmp_path, "design", {"run_id": "design-a", "at": _at(1)})
    assert canon_run_id(tmp_path, _task(started=started), RUN) == "run-1a2b3c4d"


@pytest.mark.parametrize("entry", [{"run_id": "", "at": "2026-10-25T10:01:00+00:00"},
                                   {"run_id": "design-a", "at": "not-a-time"},
                                   {"run_id": "design-a"}, "garbage", {"run_id": 7}])
def test_unusable_entries_are_ignored(tmp_path, entry):
    _history(tmp_path, "design", entry)
    assert canon_run_id(tmp_path, _task(), RUN) == NONE


@pytest.mark.parametrize("config,expected", [({}, None), ({"runId": ""}, ""),
                                             ({"runId": "  "}, "  ")])
def test_an_absent_or_blank_run_id_is_left_to_the_canon_bridge(tmp_path, config, expected):
    _history(tmp_path, "design", {"run_id": "design-a", "at": _at(1)})
    assert canon_run_id(tmp_path, _task(), config) == expected


@pytest.mark.parametrize("content", [None, "{bad", json.dumps({"phase_history": []}),
                                     json.dumps({"phase_history": {"design": {}}}), "[]"])
def test_a_missing_or_malformed_config_falls_back_to_the_runs_id(tmp_path, content):
    """The canon check then fails on its own (no history to find)."""
    if content is not None:
        (tmp_path / "shipwright_run_config.json").write_text(content, encoding="utf-8")
    assert canon_run_id(tmp_path, _task(), RUN) == "run-1a2b3c4d"

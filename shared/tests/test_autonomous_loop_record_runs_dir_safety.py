"""Regression tests for `autonomous_loop.cmd_record`'s two `runs_dir_for`
call sites (campaign-dag-scheduler R4, external Tier-3 PR review, GPT, PR
#790 round 21): neither call was wrapped for the `ValueError` `runs_dir_for`
raises on a charset-rejected id (round 9), so a malformed identifier at
either site crashed the CLI with an uncaught traceback instead of the
function's own structured-failure shape.

Split into its own file (not added to the sibling `test_autonomous_loop.py`)
because that file is already `"state": "grandfathered"` at 442 lines in
`shipwright_bloat_baseline.json` — growing a grandfathered file's `current`
needs converting it to a filed `exception` first, not a bare bump. A new
file carries no such baggage.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from autonomous_loop import cmd_record  # noqa: E402


class FakeArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def state_dir(tmp_path):
    ship = tmp_path / ".shipwright"
    ship.mkdir()
    return ship


def _make_state(state_dir, units, **overrides):
    state_path = state_dir / "loop_state.json"
    state = {
        "loop_id": "test-loop", "kind": "section", "root_session_id": "",
        "branch_strategy": "single-branch", "units": units,
    }
    state.update(overrides)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


def test_malformed_unit_arg_on_non_json_result_falls_through_not_crashes(state_dir, tmp_path, capsys):
    """First call site (fallback-result lookup): `args.unit` is raw CLI
    input, reaching `runs_dir_for` before any unit-matching happens. A
    malformed value must fall through to the existing "no fallback
    available" structured-failure path (exit 3), never an uncaught
    traceback."""
    os.chdir(tmp_path)
    _make_state(state_dir, [
        {"id": "01-auth", "status": "in_progress", "attempt": 0,
         "started_at": None, "finished_at": None, "commit": None,
         "head_sha": None, "branch": None, "result_path": None,
         "handoff_path": None, "failure_reason": None},
    ])
    args = FakeArgs(state=str(state_dir / "loop_state.json"), unit="../../etc", result="not valid json {{{")
    ret = cmd_record(args)  # must not raise
    assert ret == 3
    assert "Non-JSON" in capsys.readouterr().err


def test_malformed_persisted_unit_id_on_success_path_fails_closed_not_crashes(state_dir, tmp_path, capsys):
    """Second call site (result.json write, success path): `unit["id"]`
    here is the CANONICAL id of an already state-matched row, not raw CLI
    input — but a hand-edited/corrupted `loop_state.json` could still carry
    a charset-rejected one (the same threat model round 19 already fixed
    for `lib.loop_state._reconcile_legacy`). Must fail closed with a
    structured `recorded: false` response and never persist the write (no
    `_save_state`), not crash uncaught."""
    os.chdir(tmp_path)
    state_path = _make_state(state_dir, [
        {"id": "A/../B", "status": "in_progress", "attempt": 0,
         "started_at": None, "finished_at": None, "commit": None,
         "head_sha": None, "branch": None, "result_path": None,
         "handoff_path": None, "failure_reason": None},
    ])
    result = {"status": "failed", "error": "boom"}
    args = FakeArgs(state=str(state_path), unit="A/../B", result=json.dumps(result))
    ret = cmd_record(args)  # must not raise
    assert ret == 3
    payload = json.loads(capsys.readouterr().err)
    assert payload["recorded"] is False
    # The in-memory status mutation must never have been persisted.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["units"][0]["status"] == "in_progress"

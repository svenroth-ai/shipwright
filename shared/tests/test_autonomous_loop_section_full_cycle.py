"""Mandatory `kind == "section"` full behavioral regression test
(campaign-dag-scheduler R4, plan § R4 work breakdown item 12 / "`kind ==
"section"` compatibility, restated to cover semantics, not just arguments"):
a complete init -> next -> record -> crash -> init-resume -> finalize
sequence, asserting every return value AND every unit status matches what
today's (pre-R4) `autonomous_loop.py` produced.

This is deliberately a NEW file, not an addition to the pinned
`test_autonomous_loop.py` (zero headroom, campaign-wide constraint) — it
calls the exact same public functions that file does, the same way
(`FakeArgs` + direct `cmd_*` calls, mocked `autonomous_loop.subprocess.run`
for the two git calls `kind == "section"` has always made), so a genuine
`kind == "section"` behavior change would fail here exactly as it would have
failed there.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from autonomous_loop import cmd_finalize, cmd_init, cmd_next, cmd_record  # noqa: E402


class FakeArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def state_dir(tmp_path):
    ship = tmp_path / ".shipwright"
    ship.mkdir()
    return ship


@pytest.fixture
def units_file(tmp_path):
    config = {
        "sections": [
            {"name": "01-auth", "status": "not_started", "spec_path": "sections/01-auth.md"},
            {"name": "02-api", "status": "not_started", "spec_path": "sections/02-api.md"},
        ]
    }
    f = tmp_path / "shipwright_build_config.json"
    f.write_text(json.dumps(config), encoding="utf-8")
    return f


@patch("autonomous_loop.subprocess.run")
def test_section_init_next_record_crash_resume_finalize(mock_run, state_dir, units_file, capsys):
    mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n", "stderr": ""})()
    state_path = state_dir / "loop_state.json"

    # --- init (fresh) ---------------------------------------------------
    ret = cmd_init(FakeArgs(state=str(state_path), units_from=str(units_file),
                             kind="section", branch_strategy="single-branch", root_session_id=""))
    assert ret == 0
    init_out = json.loads(capsys.readouterr().out)
    assert init_out == {"action": "initialized", "loop_id": init_out["loop_id"], "total_units": 2}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert [u["status"] for u in state["units"]] == ["pending", "pending"]

    # --- next: picks 01-auth ---------------------------------------------
    ret = cmd_next(FakeArgs(state=str(state_path)))
    assert ret == 0
    next_out = json.loads(capsys.readouterr().out)
    assert next_out["id"] == "01-auth"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["units"][0]["status"] == "in_progress"
    assert state["units"][0]["head_sha"] == "abc123"

    # --- record: 01-auth completes successfully --------------------------
    result = {"status": "complete", "commit": "deadbeef01", "tests_passed": 3, "tests_total": 3,
              "section": "01-auth", "branch": "build/01-auth"}
    ret = cmd_record(FakeArgs(state=str(state_path), unit="01-auth", result=json.dumps(result)))
    assert ret == 0
    capsys.readouterr()  # drain cmd_record's own stdout before the next capture below
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["units"][0]["status"] == "complete"
    assert state["units"][0]["commit"] == "deadbeef01"

    # --- next: picks 02-api ----------------------------------------------
    ret = cmd_next(FakeArgs(state=str(state_path)))
    assert ret == 0
    next_out = json.loads(capsys.readouterr().out)
    assert next_out["id"] == "02-api"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["units"][1]["status"] == "in_progress"
    # `kind == "section"` never sets `branch` at `next` time (only `cmd_record`
    # does, from the result payload) — the crash below relies on exactly this.
    assert state["units"][1]["branch"] is None

    # --- CRASH: the session dies before 02-api's Task ever calls `record` -
    # no result.json exists, `branch` is still None -> the legacy salvage
    # path's branch-has-commits guess never even attempts a git call, and
    # falls straight through to the reset-to-pending fallback.

    # --- init-resume: in_progress unit triggers legacy reconcile ---------
    ret = cmd_init(FakeArgs(state=str(state_path), units_from=str(units_file),
                             kind="section", branch_strategy="single-branch", root_session_id=""))
    assert ret == 0
    resume_out = json.loads(capsys.readouterr().out)
    assert resume_out["action"] == "reconciled"
    assert len(resume_out["warnings"]) == 1
    assert "reset to pending" in resume_out["warnings"][0]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["units"][1]["status"] == "pending"
    assert state["units"][1]["attempt"] == 1  # legacy reset DOES bump attempt (unchanged pre-R4 behavior)

    # --- next: picks 02-api again, now attempt 1 --------------------------
    ret = cmd_next(FakeArgs(state=str(state_path)))
    assert ret == 0
    next_out = json.loads(capsys.readouterr().out)
    assert next_out["id"] == "02-api"
    assert next_out["attempt"] == 1

    # --- record: 02-api completes successfully -----------------------------
    result = {"status": "complete", "commit": "deadbeef02", "tests_passed": 5, "tests_total": 5,
              "section": "02-api", "branch": "build/02-api"}
    ret = cmd_record(FakeArgs(state=str(state_path), unit="02-api", result=json.dumps(result)))
    assert ret == 0
    capsys.readouterr()  # drain before finalize's own capture below

    # --- finalize: both complete, nothing outstanding ---------------------
    ret = cmd_finalize(FakeArgs(state=str(state_path)))
    assert ret == 0
    final_out = json.loads(capsys.readouterr().out)
    assert final_out["completed"] == 2
    assert final_out["failed"] == 0
    assert final_out["terminal_reason"] == "all_complete"

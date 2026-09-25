"""CLI-boundary tests for ``lib.campaign_drain`` (campaign-dag-scheduler
R5b, round 7 diff-coverage gate): ``cmd_sweep``/``cmd_run``/``main`` are the
literal entrypoints `campaign-mode.md` shells out to via `uv run ...`, and
were previously untested directly (only the pure functions they wrap were).
Split out of `test_campaign_drain.py` to keep that file under the 300-line
guideline.
"""

from __future__ import annotations

import argparse
import json
import sys

from lib.campaign_drain import cmd_run, cmd_sweep, main


def _unit(unit_id: str, status: str, **extra) -> dict:
    row = {"id": unit_id, "status": status, "attempt": 0, "attempt_id": f"a0-{unit_id}"}
    row.update(extra)
    return row


def _state(*units: dict) -> dict:
    return {"loop_id": "test-loop", "kind": "sub_iterate", "units": list(units)}


class TestCmdSweep:
    def test_success_prints_swept_json_and_returns_zero(self, tmp_path, capsys):
        state_path = tmp_path / "loop_state.json"
        state_path.write_text(json.dumps(_state(_unit("A", "pending"))), encoding="utf-8")
        rc = cmd_sweep(argparse.Namespace(state=str(state_path)))
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["swept"] == [{"id": "A", "from": "pending"}]

    def test_missing_state_file_prints_error_and_returns_one(self, tmp_path, capsys):
        rc = cmd_sweep(argparse.Namespace(state=str(tmp_path / "does-not-exist.json")))
        assert rc == 1
        assert "ERROR" in capsys.readouterr().err


class TestCmdRun:
    def test_success_prints_result_json_and_returns_zero(self, tmp_path, capsys):
        state_path = tmp_path / "loop_state.json"
        state_path.write_text(json.dumps(_state(_unit("A", "merged"))), encoding="utf-8")
        rc = cmd_run(argparse.Namespace(state=str(state_path), max_drain_seconds=1.0, poll_interval_seconds=0.0))
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["drained"] is True

    def test_missing_state_file_prints_error_and_returns_one(self, tmp_path, capsys):
        rc = cmd_run(argparse.Namespace(state=str(tmp_path / "does-not-exist.json"),
                                         max_drain_seconds=1.0, poll_interval_seconds=0.0))
        assert rc == 1
        assert "ERROR" in capsys.readouterr().err


class TestMain:
    def test_sweep_subcommand_end_to_end(self, tmp_path, monkeypatch, capsys):
        state_path = tmp_path / "loop_state.json"
        state_path.write_text(json.dumps(_state(_unit("A", "claimed"))), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["campaign_drain.py", "sweep", "--state", str(state_path)])
        assert main() == 0
        out = json.loads(capsys.readouterr().out)
        assert out["swept"] == [{"id": "A", "from": "claimed"}]

    def test_run_subcommand_end_to_end(self, tmp_path, monkeypatch):
        state_path = tmp_path / "loop_state.json"
        state_path.write_text(json.dumps(_state(_unit("A", "failed"))), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", [
            "campaign_drain.py", "run", "--state", str(state_path), "--poll-interval-seconds", "0",
        ])
        assert main() == 0

"""Escalation-path tests for `autonomous_loop.cmd_record`.

Kept out of `test_autonomous_loop.py`: that file is pinned at 442 lines in
`shipwright_bloat_baseline.json`, and growing it is an Anti-Ratchet violation.

These cover the consumer half of runner-contract Step 3.4. The runner's escalated
result carries `reason`, not the failure branch's `error`; reading only `error`
left every escalated unit with `failure_reason: None`, so the loop STRICT-STOPped
(exit 3) and the operator was told nothing about WHY. Cheap before, load-bearing
now that a CI-supply-chain re-check makes escalation a routine outcome rather than
only the rare complexity=large case.
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


class TestEscalationRecording:
    def _make_state(self, state_dir, units):
        state_path = state_dir / "loop_state.json"
        state_path.write_text(json.dumps({
            "loop_id": "loop-1", "kind": "iterate", "units": units,
        }), encoding="utf-8")
        return state_path

    def test_ci_escalation_preserves_reason_and_strict_stops(self, state_dir, tmp_path, capsys):
        """Consumer-level cover for the Step 3.4 CI escalation.

        The runner's escalated result carries `reason`, not `error` — the
        failure branch's field. Reading only `error` left every escalated unit
        with `failure_reason: None`: the loop STRICT-STOPs (exit 3) and the
        operator who picks the campaign up is told nothing about WHY it stopped.
        Cheap before, load-bearing now that a CI-supply-chain re-check makes
        escalation a routine outcome rather than only the rare complexity=large
        case. The whole result must also survive to result.json, since that is
        where `ci_paths` — the only actionable part — lives.
        """
        os.chdir(tmp_path)
        state_path = self._make_state(state_dir, [
            {"id": "3.1", "status": "in_progress", "attempt": 0,
             "started_at": None, "finished_at": None, "commit": None,
             "head_sha": None, "branch": None, "result_path": None,
             "handoff_path": None, "failure_reason": None},
        ])
        result = {
            "sub_iterate_id": "3.1",
            "status": "escalated",
            "reason": "Diff touches the CI trust boundary",
            "reason_code": "ci_supplychain_requires_operator",
            "ci_paths": [".github/workflows/ci.yml"],
        }
        args = FakeArgs(state=str(state_path), unit="3.1", result=json.dumps(result))
        ret = cmd_record(args)

        assert ret == 3, "escalation must STRICT-STOP the loop, not merge on"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        unit = state["units"][0]
        assert unit["status"] == "escalated"
        assert unit["failure_reason"] == "Diff touches the CI trust boundary"
        persisted = json.loads(
            Path(unit["result_path"]).read_text(encoding="utf-8")
        )
        assert persisted["ci_paths"] == [".github/workflows/ci.yml"]
        assert persisted["reason_code"] == "ci_supplychain_requires_operator"

    def test_failed_result_still_prefers_error_over_reason(self, state_dir, tmp_path, capsys):
        """The fallback must not change the failure branch's behaviour."""
        os.chdir(tmp_path)
        state_path = self._make_state(state_dir, [
            {"id": "01-auth", "status": "in_progress", "attempt": 0,
             "started_at": None, "finished_at": None, "commit": None,
             "head_sha": None, "branch": None, "result_path": None,
             "handoff_path": None, "failure_reason": None},
        ])
        result = {"status": "failed", "error": "Tests broken", "reason": "ignored"}
        args = FakeArgs(state=str(state_path), unit="01-auth", result=json.dumps(result))
        assert cmd_record(args) == 3
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["units"][0]["failure_reason"] == "Tests broken"

    def test_complete_result_never_gains_a_failure_reason(self, state_dir, tmp_path, capsys):
        """`_validate_result` checks `status` plus three fields, NOT the schema, so
        a `complete` result carrying a stray top-level `reason` is loop-valid. An
        unscoped fallback would stamp a failure_reason onto a GREEN unit and make
        a successful sub-iterate read as broken on the board."""
        os.chdir(tmp_path)
        state_path = self._make_state(state_dir, [
            {"id": "01-auth", "status": "in_progress", "attempt": 0,
             "started_at": None, "finished_at": None, "commit": None,
             "head_sha": None, "branch": None, "result_path": None,
             "handoff_path": None, "failure_reason": None},
        ])
        result = {
            "status": "complete", "commit": "abc123",
            "tests_passed": 3, "tests_total": 3,
            "reason": "stray field that is not a failure",
        }
        args = FakeArgs(state=str(state_path), unit="01-auth", result=json.dumps(result))
        assert cmd_record(args) == 0
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["units"][0]["status"] == "complete"
        assert state["units"][0]["failure_reason"] is None

"""``cmd_next``'s narrow ``kind == "sub_iterate"`` readiness guard clause
(campaign-dag-scheduler R1). Mirror of ``test_autonomous_loop.py``'s own
``TestNext`` fixtures — kept in a NEW file per this sub-iterate's own test
strategy (never ``test_autonomous_loop.py``, which is bloat-baseline pinned
at 442 lines with zero headroom).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from autonomous_loop import cmd_next  # noqa: E402


class FakeArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def state_dir(tmp_path):
    ship = tmp_path / ".shipwright"
    ship.mkdir()
    return ship


def _unit(id_, status="pending", depends_on=None, merged_commit=None, **extra):
    return {
        "id": id_, "spec_path": f"spec/{id_}.md", "status": status,
        "attempt": 0, "started_at": None, "finished_at": None,
        "commit": None, "head_sha": None, "branch": None,
        "result_path": None, "handoff_path": None, "failure_reason": None,
        "depends_on": depends_on or [], "merged_commit": merged_commit,
        **extra,
    }


def _write_state(state_dir, units, *, kind="sub_iterate", strategy="single-branch"):
    state_path = state_dir / "loop_state.json"
    state = {
        "loop_id": "test-loop", "kind": kind, "root_session_id": "root-123",
        "branch_strategy": strategy, "units": units,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


@patch("autonomous_loop.subprocess.run")
class TestDependsOnGuard:
    def test_dependent_unit_skipped_when_dependency_not_merged(self, mock_run, state_dir, capsys):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        state_path = _write_state(state_dir, [
            _unit("A", status="pending"),
            _unit("B", status="pending", depends_on=["A"]),
        ])
        ret = cmd_next(FakeArgs(state=str(state_path)))
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        # A is claimed FIFO (B is blocked, skipped as if it weren't there)
        assert out["id"] == "A"

    def test_dependent_unit_claimed_once_dependency_merged_and_verified(self, mock_run, state_dir, capsys):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        state_path = _write_state(state_dir, [
            _unit("A", status="merged", merged_commit="sha-a"),
            _unit("B", status="pending", depends_on=["A"]),
        ])
        ret = cmd_next(FakeArgs(state=str(state_path)))
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["id"] == "B"

    def test_merged_but_unverified_dependency_still_blocks(self, mock_run, state_dir, capsys):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        state_path = _write_state(state_dir, [
            _unit("A", status="merged", merged_commit=None),  # status says merged, ancestry unverified
            _unit("B", status="pending", depends_on=["A"]),
        ])
        ret = cmd_next(FakeArgs(state=str(state_path)))
        assert ret == 2  # nothing claimable: A isn't pending, B is blocked
        out = json.loads(capsys.readouterr().out)
        assert out["done"] is True

    def test_independent_unit_still_claimed_fifo_despite_blocked_sibling(self, mock_run, state_dir, capsys):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        state_path = _write_state(state_dir, [
            _unit("B", status="pending", depends_on=["A"]),  # listed FIRST but blocked
            _unit("A", status="pending"),
            _unit("C", status="pending"),  # independent
        ])
        ret = cmd_next(FakeArgs(state=str(state_path)))
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        # B is skipped (blocked); A is the next FIFO candidate and IS ready
        assert out["id"] == "A"

    def test_all_pending_blocked_falls_through_to_done(self, mock_run, state_dir, capsys):
        # A already failed (terminal, not "pending") — B's only pending
        # candidate depends on it and can never become ready. No unit in the
        # list is BOTH pending and ready, so cmd_next falls through to its
        # existing "done" tail (R1's documented interim-window limitation:
        # this legitimately does NOT mean the campaign finished — R4's
        # cmd_next_batch adds the correct exit code 4 for this case).
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        state_path = _write_state(state_dir, [
            _unit("A", status="failed"),
            _unit("B", status="pending", depends_on=["A"]),
        ])
        ret = cmd_next(FakeArgs(state=str(state_path)))
        assert ret == 2  # exit code contract UNCHANGED — no new exit code
        out = json.loads(capsys.readouterr().out)
        assert out["done"] is True
        # But the body is now OBSERVABLE: a blocked-but-not-finished campaign
        # is distinguishable from genuine completion (external review finding).
        assert out["blocked_pending_ids"] == ["B"]
        assert "B" in out["blockers"][0] and "A" in out["blockers"][0]
        # 3f-bis remediation (code review finding, high): the reason string
        # itself must not claim completion when units are genuinely blocked
        # — that was the actual defect, not just the presence of the fields.
        assert out["reason"] != "All units processed"
        assert out["reason"] == "Campaign stalled: pending units blocked on unmerged dependencies"

    def test_genuine_completion_has_no_blocked_fields(self, mock_run, state_dir, capsys):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        state_path = _write_state(state_dir, [
            _unit("A", status="merged", merged_commit="sha-a"),
            _unit("B", status="merged", merged_commit="sha-b"),
        ])
        ret = cmd_next(FakeArgs(state=str(state_path)))
        assert ret == 2
        out = json.loads(capsys.readouterr().out)
        assert out == {"done": True, "reason": "All units processed"}


class TestSectionKindRegressionUnaffected:
    """`kind == "section"` must see ZERO behavior change: no depends_on
    concept, no guard, no new required argument or exit code reaches
    shipwright-build's loop."""

    @patch("autonomous_loop.subprocess.run")
    def test_section_kind_ignores_depends_on_shaped_data(self, mock_run, state_dir, capsys):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        # A section unit that (hypothetically) carried a depends_on-shaped key
        # must still be claimed immediately — kind == "section" never
        # consults is_unit_ready.
        state_path = _write_state(state_dir, [
            {"id": "01-auth", "spec_path": "s/01.md", "status": "pending",
             "attempt": 0, "started_at": None, "finished_at": None,
             "commit": None, "head_sha": None, "branch": None,
             "result_path": None, "handoff_path": None, "failure_reason": None,
             "depends_on": ["nonexistent"]},
        ], kind="section")
        ret = cmd_next(FakeArgs(state=str(state_path)))
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["id"] == "01-auth"

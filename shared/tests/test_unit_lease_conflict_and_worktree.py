"""Unit tests for lib.unit_lease's ghost-touch (`stale_attempt_conflict`)
diagnostic and its `expected_campaign_worktree` cross-check
(campaign-dag-scheduler R2).

Split out of the sibling `test_unit_lease.py` purely to keep both files
under the repo's 300-line guideline after round 22's new fencing tests —
no baseline implication, this file never existed before.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.unit_lease import (
    UnitLeaseError,
    touch_unit_lease,
)


def _write_state(path: Path, units: list[dict]) -> None:
    path.write_text(json.dumps({"loop_id": "test-loop", "kind": "sub_iterate", "units": units}),
                     encoding="utf-8")


@pytest.fixture
def state_path(tmp_path) -> Path:
    p = tmp_path / ".shipwright" / "loop_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    _write_state(p, [
        {"id": "R1", "status": "merged", "commit": "deadbeef"},
        {"id": "R2", "status": "in_progress", "commit": None},
    ])
    return p


def test_touch_marks_stale_attempt_conflict_without_rejecting(state_path):
    """No fencing rejection — the touch still succeeds — but a caller CAN
    tell it touched a row whose attempt has since moved on."""
    touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=2)
    lease = touch_unit_lease(state_path, "R2", worktree="/wt-old", branch="b-old", attempt=0)
    assert lease["stale_attempt_conflict"] is True
    # Still wrote the (stale) caller's own values — no rejection.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == "R2")
    assert unit["worktree"] == "/wt-old"


def test_touch_does_not_mark_conflict_for_a_normal_same_or_higher_attempt(state_path):
    touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=0)
    lease = touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=0)
    assert lease["stale_attempt_conflict"] is False
    lease2 = touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=1)
    assert lease2["stale_attempt_conflict"] is False


def test_touch_never_marks_conflict_on_the_very_first_touch(state_path):
    lease = touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=0)
    assert lease["stale_attempt_conflict"] is False


def test_touch_accepts_a_matching_campaign_worktree(tmp_path, state_path):
    campaign_worktree = state_path.parent.parent  # state_path is <cw>/.shipwright/loop_state.json
    lease = touch_unit_lease(
        state_path, "R2", worktree="/wt", branch="b",
        expected_campaign_worktree=str(campaign_worktree),
    )
    assert lease["worktree"] == "/wt"


def test_touch_never_overwrites_an_existing_attempt_counter(state_path):
    """`attempt` on the row is owned by autonomous_loop.py's own retry
    counter (cmd_next / _reconcile_in_progress), not this module — a
    heartbeat that always touches with its own attempt=0 (the runner's real
    call shape) must never reset it (Stage-2 code review, high)."""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == "R2")
    unit["attempt"] = 2
    state_path.write_text(json.dumps(state), encoding="utf-8")

    lease = touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=0)
    assert lease["stale_attempt_conflict"] is True
    assert lease["attempt"] == 0  # the caller's own value, still echoed back

    reloaded = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in reloaded["units"] if u["id"] == "R2")
    assert unit["attempt"] == 2  # NOT reset


def test_touch_rejects_a_mismatched_campaign_worktree(tmp_path, state_path):
    other = tmp_path / "some-other-worktree"
    other.mkdir()
    with pytest.raises(UnitLeaseError, match="drifted apart"):
        touch_unit_lease(
            state_path, "R2", worktree="/wt", branch="b",
            expected_campaign_worktree=str(other),
        )

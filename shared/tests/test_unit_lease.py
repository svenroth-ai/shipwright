"""Unit tests for lib.unit_lease (campaign-dag-scheduler R2).

Covers the field-creating upsert (no fencing yet), preservation of the rest
of the row, concurrent touches serializing on the shared `loop.lock`, and the
staleness predicate.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from lib.unit_lease import (
    UnitLeaseError,
    is_unit_lease_stale,
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


def test_touch_creates_lease_fields_on_a_row_with_none_yet(state_path):
    lease = touch_unit_lease(
        state_path, "R2", worktree="/wt/campaign-x", branch="iterate/x-r2",
        attempt=0, attempt_id="a0",
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == "R2")
    for key in ("attempt", "attempt_id", "lease_touched_at", "lease_expires_at",
                "worktree", "branch"):
        assert key in unit
    assert unit["worktree"] == "/wt/campaign-x"
    assert unit["branch"] == "iterate/x-r2"
    assert lease["worktree"] == "/wt/campaign-x"


def test_touch_preserves_unrelated_fields_on_the_row(state_path):
    touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=0, attempt_id="a0")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == "R2")
    assert unit["status"] == "in_progress"
    # Sibling row is untouched.
    other = next(u for u in state["units"] if u["id"] == "R1")
    assert "lease_touched_at" not in other


def test_touch_is_a_field_creating_upsert_no_fencing(state_path):
    """No fencing-token validation applies — a second touch with a DIFFERENT
    attempt/attempt_id than the first still succeeds and simply overwrites
    (R2's stated exception until R4 adds fencing for every other mutation)."""
    touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=0, attempt_id="a0")
    lease2 = touch_unit_lease(state_path, "R2", worktree="/wt2", branch="b2",
                               attempt=1, attempt_id="a1")
    assert lease2["attempt"] == 1
    assert lease2["attempt_id"] == "a1"
    assert lease2["worktree"] == "/wt2"


def test_touch_with_no_attempt_id_preserves_an_existing_one(state_path):
    """Stage-3 doubt review (HIGH #3): `attempt_id` defaults to `None` and no
    caller today (`check_unit_lease.py`'s CLI, `sub-iterate-runner.md`'s
    brief) ever passes a real one — a default-arg heartbeat touch must not
    null out a fencing token a prior atomic claim already minted."""
    touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=0, attempt_id="a0")
    lease2 = touch_unit_lease(state_path, "R2", worktree="/wt2", branch="b2")
    assert lease2["attempt_id"] == "a0"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == "R2")
    assert unit["attempt_id"] == "a0"


def test_touch_raises_for_a_missing_unit_id(state_path):
    with pytest.raises(UnitLeaseError):
        touch_unit_lease(state_path, "R99", worktree="/wt", branch="b")


def test_touch_raises_for_a_missing_state_file(tmp_path):
    with pytest.raises(UnitLeaseError):
        touch_unit_lease(tmp_path / "nope" / "loop_state.json", "R2", worktree="/wt", branch="b")


def test_touch_finds_unit_case_insensitively(state_path):
    """Mirrors lib.loop_state.is_unit_ready's case-folded lookup convention —
    a lease touch must find the same row either lookup style would."""
    lease = touch_unit_lease(state_path, "r2", worktree="/wt", branch="b")
    assert lease["worktree"] == "/wt"


def test_lease_expires_at_is_touched_at_plus_stale_after_seconds(state_path):
    lease = touch_unit_lease(state_path, "R2", worktree="/wt", branch="b",
                              stale_after_seconds=100.0, now=1000.0)
    assert lease["lease_touched_at"] == 1000.0
    assert lease["lease_expires_at"] == 1100.0


def test_concurrent_touches_against_one_lock_file_all_succeed(state_path):
    """N concurrent runner touches serialize on loop.lock rather than
    corrupting the state file or raising."""
    errors: list[Exception] = []

    def _touch(i: int) -> None:
        try:
            touch_unit_lease(state_path, "R2", worktree=f"/wt-{i}", branch=f"b-{i}")
        except Exception as exc:  # pragma: no cover - failure path only
            errors.append(exc)

    threads = [threading.Thread(target=_touch, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors
    # File is still valid JSON with exactly the two original rows.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(state["units"]) == 2


# --- is_unit_lease_stale -----------------------------------------------------


def test_is_unit_lease_stale_false_when_no_lease_fields_yet():
    assert is_unit_lease_stale({"id": "R2"}) is False


def test_is_unit_lease_stale_false_when_not_yet_expired():
    unit = {"lease_expires_at": time.time() + 3600}
    assert is_unit_lease_stale(unit) is False


def test_is_unit_lease_stale_true_when_expired():
    unit = {"lease_expires_at": 100.0}
    assert is_unit_lease_stale(unit, now=200.0) is True


def test_is_unit_lease_stale_fails_closed_on_a_malformed_present_value():
    """A present-but-non-numeric value (hand-repaired state, a foreign
    schema, an ISO string like every other timestamp on the row) must read
    as STALE, not as a live lease that can never be reconciled again
    (doubt-reviewer, medium)."""
    assert is_unit_lease_stale({"lease_expires_at": "2026-09-22T05:00:00Z"}) is True
    assert is_unit_lease_stale({"lease_expires_at": None}) is True


# --- ghost-touch marking + campaign-worktree cross-check ---------------------


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

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


def _seed_attempt_id(state_path: Path, unit_id: str, attempt_id: str) -> None:
    """Simulates a prior atomic claim (`loop_claim._claim_unit`) having
    already minted a token — the only legitimate way a row gets one, since
    round 8's fix makes `touch_unit_lease` refuse to mint it itself."""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == unit_id)
    unit["attempt_id"] = attempt_id
    state_path.write_text(json.dumps(state), encoding="utf-8")


def test_touch_creates_lease_fields_on_a_row_with_none_yet(state_path):
    lease = touch_unit_lease(
        state_path, "R2", worktree="/wt/campaign-x", branch="iterate/x-r2", attempt=0,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == "R2")
    for key in ("attempt", "lease_touched_at", "lease_expires_at", "worktree", "branch"):
        assert key in unit
    assert unit["worktree"] == "/wt/campaign-x"
    assert unit["branch"] == "iterate/x-r2"
    assert lease["worktree"] == "/wt/campaign-x"


def test_touch_never_mints_an_attempt_id_on_a_token_less_row(state_path):
    """External Tier-3 PR review (GPT, round 8): a caller-supplied
    `attempt_id` for a row with no existing token must be REJECTED, not
    minted — `loop_claim._claim_unit` is the sole minter."""
    with pytest.raises(UnitLeaseError, match="attempt token mismatch"):
        touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt_id="a0")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == "R2")
    assert "attempt_id" not in unit
    assert "worktree" not in unit  # rejected before any lease field was mutated


def test_touch_preserves_unrelated_fields_on_the_row(state_path):
    _seed_attempt_id(state_path, "R2", "a0")
    touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=0, attempt_id="a0")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == "R2")
    assert unit["status"] == "in_progress"
    # Sibling row is untouched.
    other = next(u for u in state["units"] if u["id"] == "R1")
    assert "lease_touched_at" not in other


def test_touch_does_not_fence_on_the_attempt_int_alone(state_path):
    """The `attempt` int counter stays an unfenced diagnostic (module
    docstring's "Known limitation" — no caller passes its real value today,
    so a mismatch there is routine, not evidence of a real conflict): a
    second touch with a DIFFERENT `attempt` but the SAME `attempt_id` still
    succeeds and simply overwrites."""
    _seed_attempt_id(state_path, "R2", "a0")
    touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=0, attempt_id="a0")
    lease2 = touch_unit_lease(state_path, "R2", worktree="/wt2", branch="b2",
                               attempt=1, attempt_id="a0")
    assert lease2["attempt"] == 1
    assert lease2["worktree"] == "/wt2"


def test_touch_rejects_a_mismatched_attempt_id(state_path):
    """External Tier-3 PR review (GPT, round 7): `attempt_id` is a real
    fencing token with no false-positive case — unlike `attempt` above, a
    caller that supplies one is enforced against the row's current token,
    and a mismatch must reject before mutating any lease field."""
    _seed_attempt_id(state_path, "R2", "a0")
    touch_unit_lease(state_path, "R2", worktree="/wt", branch="b", attempt=0, attempt_id="a0")
    with pytest.raises(UnitLeaseError, match="attempt token mismatch"):
        touch_unit_lease(state_path, "R2", worktree="/wt2", branch="b2",
                          attempt=1, attempt_id="a1")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == "R2")
    assert unit["worktree"] == "/wt"
    assert unit["attempt_id"] == "a0"


def test_touch_with_matching_attempt_id_preserves_it(state_path):
    """Stage-3 doubt review (HIGH #3): `attempt_id` defaults to `None` — a
    touch that DOES supply the row's real current token must not null it
    out or otherwise disturb it; the field is only ever echoed back, never
    minted or cleared, by this function."""
    _seed_attempt_id(state_path, "R2", "a0")
    lease2 = touch_unit_lease(state_path, "R2", worktree="/wt2", branch="b2", attempt_id="a0")
    assert lease2["attempt_id"] == "a0"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == "R2")
    assert unit["attempt_id"] == "a0"


def test_touch_with_no_attempt_id_on_a_claimed_sub_iterate_row_is_rejected(state_path):
    """External Tier-3 PR review (GPT, PR #790 round 22): SUPERSEDES the
    former `test_touch_with_no_attempt_id_preserves_an_existing_one` — that
    test asserted a tokenless touch of an already-claimed row SUCCEEDED
    (defending only against nulling the token out). Round 22 closes the
    real gap that shape left open: ANY caller — a stale runner whose claim
    was reclaimed, in particular — could omit `--attempt-id` entirely and
    still mutate a claimed row's lease fields, extending
    `lease_expires_at` indefinitely with no proof of current ownership. A
    `kind == "sub_iterate"` row that already carries a real token must now
    REQUIRE one on every touch; a tokenless touch is rejected before any
    lease field is mutated."""
    _seed_attempt_id(state_path, "R2", "a0")
    with pytest.raises(UnitLeaseError, match="attempt token required"):
        touch_unit_lease(state_path, "R2", worktree="/wt2", branch="b2")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == "R2")
    assert unit["attempt_id"] == "a0"  # unchanged
    assert "worktree" not in unit  # rejected before any lease field was mutated


def test_touch_with_no_attempt_id_on_a_claimed_section_row_still_succeeds(state_path):
    """Round 22's new requirement is scoped to `kind == "sub_iterate"` — the
    only kind `attempt_id` is ever minted for. A `kind == "section"` state
    (pre-R4 build-orchestrator campaigns, a different `loop_state.json`
    shape entirely) must behave exactly as before: a tokenless touch still
    succeeds even if the row happens to carry an `attempt_id`-shaped field
    (which no real section row ever does — this only proves the kind gate
    itself, not a real production shape)."""
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["kind"] = "section"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    _seed_attempt_id(state_path, "R2", "a0")

    lease = touch_unit_lease(state_path, "R2", worktree="/wt2", branch="b2")
    assert lease["worktree"] == "/wt2"


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


# Ghost-touch marking (`stale_attempt_conflict`) and the
# `expected_campaign_worktree` cross-check are covered in the sibling
# `test_unit_lease_conflict_and_worktree.py`.

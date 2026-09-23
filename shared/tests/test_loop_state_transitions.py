"""Unit tests for the R4 9-state machine + edge table and
``reconcile_in_progress``'s ``kind``-based dispatch in ``lib.loop_state``.

Fencing primitives / path helpers / finalize-summary / record-status
mapping live in the sibling ``test_loop_state_fencing.py`` — split purely to
keep each file comfortably under the repo's 300-line guideline; neither is
bloat-baseline pinned.
"""

from __future__ import annotations

import pytest

from lib import loop_state
from lib.loop_state import (
    ACTIVE,
    RESUMABLE,
    STATES,
    TRANSITIONS,
    is_legal_transition,
    reconcile_in_progress,
)


class TestStateMachineData:
    def test_nine_states_exactly(self):
        assert STATES == {
            "pending", "claimed", "running", "built", "reviewed",
            "merging", "merged", "failed", "held",
        }

    def test_terminal_active_resumable_partition_non_terminal(self):
        # every non-TERMINAL state is either ACTIVE or RESUMABLE, and the
        # two never overlap
        assert ACTIVE & RESUMABLE == set()
        assert ACTIVE | RESUMABLE | loop_state.TERMINAL == STATES

    @pytest.mark.parametrize("from_state,to_state,legal", [
        ("pending", "claimed", True),
        ("pending", "held", True),
        ("pending", "running", False),
        ("claimed", "running", True),
        ("claimed", "pending", True),
        ("claimed", "failed", True),
        ("claimed", "held", True),
        ("claimed", "merged", False),
        ("running", "built", True),
        ("running", "failed", True),
        ("running", "pending", True),
        ("running", "held", True),
        ("built", "reviewed", True),
        ("built", "merging", True),
        ("built", "failed", True),
        ("built", "held", True),
        ("built", "pending", False),
        ("reviewed", "merging", True),
        ("reviewed", "built", True),
        ("reviewed", "held", True),
        ("reviewed", "failed", False),
        ("merging", "merged", True),
        ("merging", "held", True),
        ("merging", "failed", True),
        ("held", "pending", True),
        ("held", "claimed", False),
        ("merged", "pending", False),
        ("failed", "pending", False),
    ])
    def test_edge_table_exhaustive(self, from_state, to_state, legal):
        assert is_legal_transition(from_state, to_state) is legal

    def test_unknown_state_never_legal(self):
        assert not is_legal_transition("bogus", "pending")
        assert not is_legal_transition("pending", "bogus")

    def test_forced_crosses_any_real_edge(self):
        # cmd_mark's exemption: any two REAL states, any direction
        assert is_legal_transition("merged", "pending", forced=True)
        assert is_legal_transition("failed", "held", forced=True)

    def test_forced_still_rejects_an_unknown_target_state(self):
        """`to_state` must always be a real STATES member, forced or not —
        the exemption is about crossing FROM anywhere, not landing nowhere."""
        assert not is_legal_transition("pending", "bogus", forced=True)
        assert not is_legal_transition("bogus", "bogus", forced=True)

    def test_forced_accepts_a_legacy_or_unknown_from_state(self):
        """Stage-3 doubt review (HIGH #2): `cmd_mark --force` is the one
        documented operator escape hatch for a row stuck on a pre-R4 legacy
        status (`"complete"`, `"escalated"`, `"in_progress"` — a
        never-claimed row's own `resolve_record_status`/
        `enforce_record_fencing` pass-through, or `_reconcile_legacy`'s own
        legacy write). Gating the exemption on `from_state` too made that
        hatch unable to reach the exact rows that most need it — a row on
        ANY from-state (real, legacy, or simply unknown) may cross to a
        real target under `forced=True`; only the target is still checked."""
        assert is_legal_transition("complete", "pending", forced=True)
        assert is_legal_transition("escalated", "held", forced=True)
        assert is_legal_transition("in_progress", "merged", forced=True)
        assert is_legal_transition("bogus", "pending", forced=True)

    def test_transitions_table_keys_are_every_state(self):
        assert set(TRANSITIONS) == STATES

    def test_merged_and_failed_are_dead_ends(self):
        assert TRANSITIONS["merged"] == frozenset()
        assert TRANSITIONS["failed"] == frozenset()


def _unit(**overrides) -> dict:
    unit = {"id": "A", "status": "running", "attempt": 0}
    unit.update(overrides)
    return unit


class TestReconcileDispatch:
    def test_sub_iterate_dispatches_to_lease_based(self, monkeypatch):
        seen = []
        monkeypatch.setattr(loop_state, "_reconcile_leases", lambda s: seen.append("leases") or [])
        monkeypatch.setattr(loop_state, "_reconcile_legacy", lambda s, p: seen.append("legacy") or [])
        reconcile_in_progress({"units": []}, "sub_iterate", "/tmp/.shipwright/loop_state.json")
        assert seen == ["leases"]

    def test_section_and_unknown_dispatch_to_legacy(self, monkeypatch):
        seen = []
        monkeypatch.setattr(loop_state, "_reconcile_leases", lambda s: seen.append("leases") or [])
        monkeypatch.setattr(loop_state, "_reconcile_legacy", lambda s, p: seen.append("legacy") or [])
        reconcile_in_progress({"units": []}, "section", "/tmp/x")
        reconcile_in_progress({"units": []}, None, "/tmp/x")
        assert seen == ["legacy", "legacy"]


class TestReconcileLeases:
    def test_never_leased_running_unit_resets_to_pending_no_attempt_bump(self):
        state = {"units": [_unit(status="running", attempt=0)]}
        warnings = reconcile_in_progress(state, "sub_iterate", "/tmp/x")
        assert state["units"][0]["status"] == "pending"
        assert state["units"][0]["attempt"] == 0  # reclaim never bumps attempt
        assert "never touched" in warnings[0]

    def test_expired_lease_resets_to_pending(self):
        state = {"units": [_unit(status="claimed", lease_expires_at=1.0)]}
        warnings = reconcile_in_progress(state, "sub_iterate", "/tmp/x")
        assert state["units"][0]["status"] == "pending"
        assert "expired" in warnings[0]

    def test_live_lease_left_alone(self):
        state = {"units": [_unit(status="running", lease_expires_at=9_999_999_999.0)]}
        warnings = reconcile_in_progress(state, "sub_iterate", "/tmp/x")
        assert state["units"][0]["status"] == "running"
        assert warnings == []

    def test_merging_never_touched_by_lease_reconcile(self):
        # merging has no associated lease (see module docstring) — must be
        # left completely alone by the sub_iterate reconcile path.
        state = {"units": [_unit(status="merging")]}
        warnings = reconcile_in_progress(state, "sub_iterate", "/tmp/x")
        assert state["units"][0]["status"] == "merging"
        assert warnings == []

    def test_terminal_and_pending_units_untouched(self):
        state = {"units": [_unit(status="merged"), _unit(id="B", status="pending")]}
        reconcile_in_progress(state, "sub_iterate", "/tmp/x")
        assert state["units"][0]["status"] == "merged"
        assert state["units"][1]["status"] == "pending"

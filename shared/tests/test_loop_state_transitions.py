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
    cmd_init_sub_iterate_payload,
    handoff_dir_for,
    is_legal_transition,
    reconcile_in_progress,
    runs_dir_for,
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


class TestCmdInitLegacyTerminalStatuses:
    def test_legacy_terminal_statuses_fall_through_to_reinit_not_false_resumed(self, tmp_path):
        """External Tier-3 PR review (GPT, round 5, PR #790): a pre-R4
        campaign whose rows are still marked `"complete"`, `"failed"`
        (legacy string, not the new-vocab terminal reuse), or `"escalated"`
        match none of ACTIVE/`"in_progress"`/RESUMABLE — the old `if units:`
        fallback in `cmd_init_sub_iterate_payload` reported these as
        `{"action": "resumed", "pending": 0}` without ever checking they
        were verified TERMINAL under the new vocabulary. `"escalated"`
        specifically means unresolved human action, not done; silently
        reporting it as resumed/nothing-pending would hide that. Must fall
        through to a genuine reinit instead, exactly like `kind == "section"`
        always has for a fully-done state."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        existing = {"units": [_unit(status="complete"), _unit(id="B", status="escalated")]}
        payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
        assert payload == {}
        assert mutated is False


class TestPathHelpersRejectAMalformedLoopId:
    """External Tier-3 PR review (GPT, round 9): `runs_dir_for` and
    `handoff_dir_for` trusted the persisted `loop_id` directly — a
    hand-edited or corrupted state file could carry a traversing value.
    Charset-checked the same way `rejected_payload_path` already checks
    `unit_id` (round 6)."""

    def test_runs_dir_for_rejects_a_traversing_loop_id(self, tmp_path):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        with pytest.raises(ValueError, match="not a safe identifier"):
            runs_dir_for(state_path, "../../etc", "A")

    def test_handoff_dir_for_rejects_a_traversing_loop_id(self, tmp_path):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        with pytest.raises(ValueError, match="not a safe identifier"):
            handoff_dir_for(state_path, "../../etc")

    def test_runs_dir_for_rejects_a_malformed_persisted_unit_id(self, tmp_path):
        """External Tier-3 PR review (GPT, round 11): `runs_dir_for` charset-
        checked `loop_id` but appended `unit_id` unvalidated — a hand-edited
        or corrupted state row's `id` could redirect a write meant for one
        unit into another's directory, or outside the loop root entirely.
        `A/../B` in particular never trips a naive containment check alone
        (it resolves to the sibling `runs/{loop_id}/B/`, which IS inside the
        loop root) — the charset check is what refuses it, the same
        realization `rejected_payload_path`'s own docstring already recorded
        for this exact string shape."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        with pytest.raises(ValueError, match="not a safe identifier"):
            runs_dir_for(state_path, "test-loop", "A/../B")

    def test_runs_dir_for_unit_id_containment_is_defense_in_depth(self, tmp_path):
        """A `unit_id` that clears the charset (no literal `/` or `..`) but
        somehow still resolved outside the loop root would be caught by the
        post-append containment re-check — belt-and-suspenders alongside the
        charset gate, matching the `loop_id` check's own shape above."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        # A charset-safe unit_id resolves inside the loop root normally.
        result = runs_dir_for(state_path, "test-loop", "A")
        assert result == runs_dir_for(state_path, "test-loop") / "A"

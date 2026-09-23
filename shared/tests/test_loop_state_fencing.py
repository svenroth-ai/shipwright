"""Unit tests for the R4 fencing primitives, canonical state-root path
helpers, ``cmd_init``/``cmd_finalize`` sub_iterate decision bodies, and the
``cmd_record`` status-mapping/fencing glue in ``lib.loop_state``.

Split from the sibling ``test_loop_state_transitions.py`` purely to keep
each file comfortably under the repo's 300-line guideline.
"""

from __future__ import annotations

import json

import pytest

from lib import loop_state
from lib.loop_state import (
    cmd_init_sub_iterate_payload,
    enforce_record_fencing,
    find_unit_row,
    handoff_dir_for,
    is_valid_sha,
    now_iso,
    rejected_payload_path,
    resolve_record_status,
    runs_dir_for,
    sub_iterate_finalize_summary,
    validate_attempt_token,
)

_FAKE_SHA = "deadbeef" * 5


def _unit(**overrides) -> dict:
    unit = {"id": "A", "status": "running", "attempt": 0}
    unit.update(overrides)
    return unit


class TestFencingPrimitives:
    def test_is_valid_sha_accepts_40_char_hex(self):
        assert is_valid_sha(_FAKE_SHA)

    def test_is_valid_sha_rejects_everything_else(self):
        for bad in ("short", "deadbeef", None, 123, "g" * 40, "--evil"):
            assert not is_valid_sha(bad)

    def test_validate_attempt_token_match(self):
        unit = {"id": "A", "attempt_id": "loop1-A-a0"}
        assert validate_attempt_token(unit, "loop1-A-a0")

    def test_validate_attempt_token_mismatch(self):
        unit = {"id": "A", "attempt_id": "loop1-A-a0"}
        assert not validate_attempt_token(unit, "loop1-A-a1")

    def test_validate_attempt_token_none_unit_or_empty_token(self):
        assert not validate_attempt_token(None, "x")
        assert not validate_attempt_token({"attempt_id": "x"}, None)
        assert not validate_attempt_token({"attempt_id": "x"}, "")

    def test_find_unit_row_exact_then_case_fold(self):
        state = {"units": [{"id": "R0"}, {"id": "b"}]}
        assert find_unit_row(state, "R0")["id"] == "R0"
        assert find_unit_row(state, "r0")["id"] == "R0"
        assert find_unit_row(state, "missing") is None


class TestPathHelpers:
    def test_runs_dir_for_is_state_root_relative_not_cwd(self, tmp_path, monkeypatch):
        other = tmp_path / "somewhere-else-entirely"
        other.mkdir()
        monkeypatch.chdir(other)
        state_path = tmp_path / "project" / ".shipwright" / "loop_state.json"
        result = runs_dir_for(state_path, "loop1", "A")
        assert result == (tmp_path / "project" / ".shipwright" / "runs" / "loop1" / "A")

    def test_rejected_payload_path(self, tmp_path):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        p = rejected_payload_path(state_path, "loop1", "A", "loop1-A-a1")
        assert p == tmp_path / ".shipwright" / "runs" / "loop1" / "A" / "rejected" / "loop1-A-a1.json"

    def test_rejected_payload_path_rejects_traversing_unit_id(self, tmp_path):
        """Stage-2 code review (medium, security): a traversing `unit_id`
        must be rejected before any write is attempted. Now caught by the
        earlier `id_charset_ok` gate (external review, high) — no `/` is in
        the allowed charset at all, so this specific shape never reaches the
        loop-root containment assert any more; that assert stays as
        defense-in-depth for a shape the charset check doesn't anticipate."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        with pytest.raises(ValueError, match="not a safe identifier"):
            rejected_payload_path(state_path, "loop1", "../../etc", "loop1-A-a1")

    def test_handoff_dir_for(self, tmp_path):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        assert handoff_dir_for(state_path, "loop1") == tmp_path / ".shipwright" / "planning" / "handoffs" / "loop1"


class TestCmdInitSubIteratePayload:
    def test_active_unit_triggers_reconcile_and_mutates(self, tmp_path):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        existing = {"units": [_unit(status="running")]}
        payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
        assert mutated is True
        assert payload["action"] == "reconciled"
        assert existing["units"][0]["status"] == "pending"  # never-leased -> reclaimed

    def test_resumable_unit_reports_resumed_without_mutating(self, tmp_path):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        existing = {"units": [_unit(status="built"), _unit(id="B", status="held")]}
        payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
        assert mutated is False
        assert payload == {"action": "resumed", "pending": 2}

    def test_all_terminal_resumes_with_zero_pending_not_reinit(self, tmp_path):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        existing = {"units": [_unit(status="merged"), _unit(id="B", status="failed")]}
        payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
        assert mutated is False
        assert payload == {"action": "resumed", "pending": 0}

    def test_empty_unit_list_signals_reinit(self, tmp_path):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        payload, mutated = cmd_init_sub_iterate_payload(state_path, {"units": []})
        assert payload == {}
        assert mutated is False

    def test_legacy_terminal_statuses_fall_through_to_reinit_not_false_resumed(self, tmp_path):
        """External Tier-3 PR review (GPT, round 5): a pre-R4 campaign whose
        rows are still marked `"complete"`, `"failed"` (legacy string, not
        the new-vocab terminal reuse), or `"escalated"` match none of
        ACTIVE/`"in_progress"`/RESUMABLE — the old `if units:` fallback
        reported these as `{"action": "resumed", "pending": 0}` without ever
        checking they were verified TERMINAL under the new vocabulary.
        `"escalated"` specifically means unresolved human action, not done;
        silently reporting it as resumed/nothing-pending would hide that.
        Must fall through to a genuine reinit instead, exactly like
        `kind == "section"` always has for a fully-done state."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        existing = {"units": [_unit(status="complete"), _unit(id="B", status="escalated")]}
        payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
        assert payload == {}
        assert mutated is False

    def test_legacy_in_progress_unit_is_reconciled_not_silently_resumed(self, tmp_path):
        """External code review (GLM, high): a unit still carrying the
        pre-R4 `cmd_next` status `"in_progress"` (the live status for
        `--branch-strategy serial` sub_iterate campaigns) is neither ACTIVE
        nor RESUMABLE nor TERMINAL — it must never fall through to a silent
        `{"action": "resumed", "pending": 0}`.

        Scoped-review fix (low, finding G): fixture now carries `"kind":
        "sub_iterate"` — production's only call site never invokes this
        function on any other kind, and the omission previously routed this
        test through `_reconcile_legacy`'s non-sub_iterate attempt-bump
        branch, contradicting the sibling test below which asserts the
        sub_iterate branch never bumps `attempt` on this exact fallback.
        The attempt assertion moves to that sibling."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        existing = {"loop_id": "loop1", "kind": "sub_iterate", "units": [_unit(status="in_progress")]}
        payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
        assert mutated is True
        assert payload["action"] == "reconciled"
        # `_reconcile_legacy`'s own fallback: no result.json/branch evidence
        # found -> reset to pending.
        assert existing["units"][0]["status"] == "pending"

    def test_legacy_in_progress_sub_iterate_maps_complete_result_onto_merged(self, tmp_path, monkeypatch):
        """Stage-3 doubt review (HIGH #2, second half): a `kind ==
        "sub_iterate"` row reconciled via a found `result.json` must land
        on the 9-state vocabulary (`"merged"`, TERMINAL) — not the legacy
        `"complete"` string the new claim/mark/finalize machinery does not
        understand — with `merged_commit` set so
        `sub_iterate_finalize_summary`'s own commit list picks it up.

        Scoped-review fix (high): `result.json`'s commit is a pre-merge
        branch tip, never a verified merge, so production routes it through
        `verify_merged_commit_ancestry` before trusting it — stubbed here to
        `lambda c: c` (matching `test_loop_state.py`'s own convention) so
        this test keeps asserting the SHA without a real git fetch."""
        monkeypatch.setattr(loop_state, "verify_merged_commit_ancestry", lambda c: c)
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        runs_dir = state_path.parent / "runs" / "loop1" / "A"
        runs_dir.mkdir(parents=True)
        (runs_dir / "result.json").write_text(
            json.dumps({"status": "complete", "commit": _FAKE_SHA}), encoding="utf-8")
        existing = {"loop_id": "loop1", "kind": "sub_iterate", "units": [_unit(status="in_progress")]}
        payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
        assert mutated is True
        unit = existing["units"][0]
        assert unit["status"] == "merged"
        assert unit["merged_commit"] == _FAKE_SHA

    def test_legacy_in_progress_sub_iterate_result_json_never_marks_merged_when_unverified(
        self, tmp_path, monkeypatch,
    ):
        """External review (GPT, high): an unverified `result.json` commit
        must not flip `status` to `"merged"` (TERMINAL) — that would be the
        false completion `sub_iterate_finalize_summary` publishes as done.
        Falls through to the same reset-to-pending fallback an absent
        result.json would hit."""
        monkeypatch.setattr(loop_state, "verify_merged_commit_ancestry", lambda c: None)
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        runs_dir = state_path.parent / "runs" / "loop1" / "A"
        runs_dir.mkdir(parents=True)
        (runs_dir / "result.json").write_text(
            json.dumps({"status": "complete", "commit": _FAKE_SHA}), encoding="utf-8")
        existing = {"loop_id": "loop1", "kind": "sub_iterate", "units": [_unit(status="in_progress")]}
        payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
        assert mutated is True
        unit = existing["units"][0]
        assert unit["status"] == "pending"
        assert "merged_commit" not in unit

    def test_legacy_in_progress_sub_iterate_pending_fallback_never_double_bumps(self, tmp_path):
        """Stage-3 doubt review (LOW #2): a `kind == "sub_iterate"` row with
        no result.json/branch evidence falls back to `"pending"` here — a
        real state both vocabularies share — WITHOUT this function bumping
        `attempt`. `_claim_unit`'s own `attempt_id is None` sentinel already
        bumps it exactly once on the row's actual next claim; bumping here
        too would double-count the row's first retry."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        existing = {"loop_id": "loop1", "kind": "sub_iterate", "units": [_unit(status="in_progress")]}
        payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
        assert mutated is True
        unit = existing["units"][0]
        assert unit["status"] == "pending"
        assert unit["attempt"] == 0

    def test_legacy_in_progress_alongside_active_unit_both_reconciled(self, tmp_path):
        """A mixed campaign — one unit claimed via the new flow (`running`),
        one still carrying the legacy `in_progress` status — reconciles
        both, never dropping the legacy one."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        existing = {"loop_id": "loop1", "units": [_unit(status="running"), _unit(id="B", status="in_progress")]}
        payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
        assert mutated is True
        assert payload["action"] == "reconciled"
        assert existing["units"][0]["status"] == "pending"
        assert existing["units"][1]["status"] == "pending"


class TestSubIterateFinalizeSummary:
    def test_refuses_outside_terminal(self):
        state = {"units": [_unit(status="running"), _unit(id="B", status="merged")]}
        error, summary = sub_iterate_finalize_summary(state)
        assert summary is None
        assert error["non_terminal_ids"] == ["A"]

    def test_summarizes_when_all_terminal(self):
        state = {
            "loop_id": "loop1", "kind": "sub_iterate",
            "units": [
                _unit(status="merged", merged_commit=_FAKE_SHA),
                _unit(id="B", status="failed"),
                _unit(id="C", status="held"),
            ],
        }
        error, summary = sub_iterate_finalize_summary(state)
        assert error is None
        assert summary["merged"] == 1 and summary["failed"] == 1 and summary["held"] == 1
        assert summary["commits"] == [_FAKE_SHA]


class TestResolveRecordStatus:
    def test_never_claimed_row_passes_through_unchanged(self):
        # attempt_id absent -> today's production loop, pre-R5a: unchanged.
        assert resolve_record_status("sub_iterate", {"id": "A"}, "complete") == "complete"
        assert resolve_record_status("sub_iterate", {"id": "A"}, "escalated") == "escalated"

    def test_claimed_row_maps_complete_to_built(self):
        unit = {"id": "A", "attempt_id": "loop1-A-a0"}
        assert resolve_record_status("sub_iterate", unit, "complete") == "built"

    def test_claimed_row_maps_everything_else_to_failed(self):
        unit = {"id": "A", "attempt_id": "loop1-A-a0"}
        assert resolve_record_status("sub_iterate", unit, "failed") == "failed"
        assert resolve_record_status("sub_iterate", unit, "escalated") == "failed"

    def test_section_kind_never_remapped_even_if_attempt_id_present(self):
        unit = {"id": "01-auth", "attempt_id": "whatever"}
        assert resolve_record_status("section", unit, "complete") == "complete"


class TestEnforceRecordFencing:
    def test_never_claimed_unit_skips_check_entirely(self, tmp_path):
        # campaign-mode.md step 3f compatibility: no attempt_id on the row
        # -> no --attempt-id required, no rejection, ever.
        state_peek = {"loop_id": "loop1", "units": [{"id": "A"}]}
        assert enforce_record_fencing(tmp_path / ".shipwright" / "loop_state.json",
                                       state_peek, "A", None, "{}") is None

    def test_claimed_unit_requires_attempt_id(self, tmp_path):
        state_peek = {"loop_id": "loop1", "units": [{"id": "A", "attempt_id": "loop1-A-a0"}]}
        assert enforce_record_fencing(tmp_path / ".shipwright" / "loop_state.json",
                                       state_peek, "A", None, "{}") == 1

    def test_claimed_unit_stale_token_rejected_and_parked(self, tmp_path):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        state_peek = {"loop_id": "loop1", "units": [{"id": "A", "attempt_id": "loop1-A-a1"}]}
        raw = json.dumps({"status": "complete"})
        code = enforce_record_fencing(state_path, state_peek, "A", "loop1-A-a0", raw)
        assert code == 5
        parked = rejected_payload_path(state_path, "loop1", "A", "loop1-A-a0")
        assert parked.exists()
        assert parked.read_text(encoding="utf-8") == raw

    def test_claimed_unit_matching_token_proceeds(self, tmp_path):
        state_peek = {"loop_id": "loop1", "units": [{"id": "A", "attempt_id": "loop1-A-a0"}]}
        assert enforce_record_fencing(tmp_path / ".shipwright" / "loop_state.json",
                                       state_peek, "A", "loop1-A-a0", "{}") is None


def test_now_iso_is_iso_format_utc():
    ts = now_iso()
    assert "T" in ts and ("+00:00" in ts or ts.endswith("Z"))

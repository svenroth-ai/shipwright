"""Unit tests for ``lib.loop_state``'s ``cmd_init_sub_iterate_payload`` and
the legacy ``_reconcile_legacy`` path it drives for a ``kind ==
"sub_iterate"`` row stuck at the pre-R4 ``"in_progress"`` status.

Split out of the sibling ``test_loop_state_fencing.py`` (round 19) purely to
keep that file under the repo's 300-line guideline after its malformed-
unit-id regression test — no baseline implication, this file never existed
before.
"""

from __future__ import annotations

import json

from lib import loop_state
from lib.loop_state import cmd_init_sub_iterate_payload

_FAKE_SHA = "deadbeef" * 5


def _unit(**overrides) -> dict:
    unit = {"id": "A", "status": "running", "attempt": 0}
    unit.update(overrides)
    return unit


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

    def test_legacy_reconcile_fails_closed_on_a_malformed_persisted_unit_id(self, tmp_path):
        """External Tier-3 PR review (GPT, round 19): `_reconcile_legacy`
        previously concatenated the persisted `unit["id"]` directly into
        `runs_dir / unit["id"] / "result.json"`, unvalidated — the same
        traversal threat model `runs_dir_for`'s own `unit_id` parameter
        (round 11) already exists to close, just not routed through here.
        `A/../B` resolves to the sibling `runs/{loop_id}/B/` (a naive
        containment check alone would miss it — the charset gate is what
        refuses it), so a real `result.json` is planted at EXACTLY that
        sibling path to prove it is never read: the malformed id must fail
        closed (this unit falls through to the ordinary reset-to-pending
        fallback), never crash the whole reconcile sweep and never mark
        the unit complete from a file it was never entitled to look at."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        sibling_runs_dir = state_path.parent / "runs" / "loop1" / "B"
        sibling_runs_dir.mkdir(parents=True)
        (sibling_runs_dir / "result.json").write_text(
            json.dumps({"status": "complete", "commit": _FAKE_SHA}), encoding="utf-8")
        existing = {"loop_id": "loop1", "kind": "sub_iterate",
                    "units": [_unit(id="A/../B", status="in_progress")]}
        payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
        assert mutated is True
        unit = existing["units"][0]
        assert unit["status"] == "pending"  # never "merged" — the sibling file was never read
        assert "merged_commit" not in unit

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

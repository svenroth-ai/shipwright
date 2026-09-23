"""Regression tests for two `autonomous_loop.py` fixes from campaign
`campaign-dag-scheduler` R4's Stage-3 doubt review (4 HIGH + 1 medium + 2 low
against PR #790). Split into its own, new, under-budget file rather than
grown into `shared/tests/test_autonomous_loop.py` (itself already
grandfathered at 442/300, per that file's own baseline entry) — mirrors the
`test_autonomous_loop_lease_reconcile.py` precedent this same campaign's R2
already established for the identical reason.

- **HIGH #1** (`TestFinalizeSubIterateLegacyCompat`): `cmd_finalize`'s
  `kind == "sub_iterate"` dispatch must fall through to the untouched legacy
  summary path for a campaign that has never been touched by the new
  atomic-claim flow, instead of hard-refusing on legacy vocabulary it does
  not understand.
- **LOW #1** (`TestRecordSubIterateCaseFold`): `cmd_record`'s mutation
  write-loop must use the SAME case-fold-aware lookup as its own fencing
  pre-check, so a case-mismatched `--unit` is genuinely found and recorded
  (or hard-fails if truly nonexistent) rather than silently no-op'd while
  still reporting success.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from autonomous_loop import cmd_finalize, cmd_record


class FakeArgs:
    """Minimal argparse.Namespace substitute (mirrors test_autonomous_loop.py)."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestFinalizeSubIterateLegacyCompat:
    """A `kind == "sub_iterate"` campaign that has never been touched by the
    new atomic-claim flow (no unit carries a real `attempt_id`) must
    finalize EXACTLY as it did before the strict `sub_iterate_finalize_summary`
    branch existed — i.e. it falls through to the same legacy summary logic
    `kind == "section"` still uses, and never hard-refuses on an
    incomplete/legacy-vocabulary unit."""

    def test_all_legacy_vocabulary_state_finalizes_successfully(self, tmp_path, capsys):
        """A never-claimed `sub_iterate` campaign carrying pre-R4 statuses,
        INCLUDING a still-pending unit, must still exit 0 with the legacy
        summary shape -- the pre-diff behavior this regression pins."""
        state_path = tmp_path / "loop_state.json"
        state = {
            "loop_id": "test-loop",
            "kind": "sub_iterate",
            "units": [
                {"id": "R1", "status": "complete", "commit": "abc"},
                {"id": "R2", "status": "escalated", "commit": None},
                {"id": "R3", "status": "pending", "commit": None},
            ],
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        args = FakeArgs(state=str(state_path))
        ret = cmd_finalize(args)
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["completed"] == 1
        assert out["failed"] == 0
        assert out["escalated"] == 1
        assert out["pending"] == 1

    def test_new_flow_touched_state_still_uses_the_strict_finalize(self, tmp_path, capsys):
        """Once ANY unit carries a real `attempt_id` (the campaign HAS been
        touched by `loop_claim.cmd_next_batch`), the strict `TERMINAL`-only
        finalize applies as designed -- a non-TERMINAL unit still refuses."""
        state_path = tmp_path / "loop_state.json"
        state = {
            "loop_id": "test-loop",
            "kind": "sub_iterate",
            "units": [
                {"id": "R1", "status": "merged", "attempt_id": "test-loop-R1-a0",
                 "merged_commit": "abc"},
                {"id": "R2", "status": "running", "attempt_id": "test-loop-R2-a0"},
            ],
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        args = FakeArgs(state=str(state_path))
        ret = cmd_finalize(args)
        assert ret == 1
        err = json.loads(capsys.readouterr().err)
        assert err["non_terminal_ids"] == ["R2"]


class TestRecordSubIterateCaseFold:
    """`cmd_record`'s fencing pre-check uses `find_unit_row` (case-fold-aware),
    but its own MUTATION lookup was exact-match only — a case-mismatched
    `--unit` passed the fence, found no row in the write loop, and still
    silently reported `{"recorded": true}` / exit 0."""

    def _make_state(self, tmp_path, units):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {"loop_id": "test-loop", "kind": "sub_iterate", "units": units}
        state_path.write_text(json.dumps(state), encoding="utf-8")
        return state_path

    def test_case_mismatched_unit_is_found_and_recorded_not_silently_dropped(self, tmp_path, capsys):
        """The fencing pre-check's `find_unit_row` (case-fold) already
        matched `--unit r1` against row `R1` and let it through; before this
        fix, the write loop below used an EXACT-match lookup, found nothing,
        and still printed `{"recorded": true}` / exit 0 without ever
        touching the row. Now both lookups agree: the row is genuinely
        found (case-fold) AND updated."""
        os.chdir(tmp_path)
        state_path = self._make_state(tmp_path, [
            {"id": "R1", "status": "running", "attempt_id": "test-loop-R1-a0"},
        ])
        result = {"status": "complete", "commit": "abc123", "tests_passed": 5, "tests_total": 5}
        args = FakeArgs(state=str(state_path), unit="r1", attempt_id="test-loop-R1-a0",
                         result=json.dumps(result))
        ret = cmd_record(args)
        assert ret == 0
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["units"][0]["status"] == "built"
        assert state["units"][0]["commit"] == "abc123"

    def test_genuinely_nonexistent_unit_hard_fails_instead_of_silently_succeeding(self, tmp_path, capsys):
        """A `--unit` that matches NO row even case-folded (unlike the test
        above) must hard-fail, not silently report `{"recorded": true}`."""
        os.chdir(tmp_path)
        state_path = self._make_state(tmp_path, [
            {"id": "R1", "status": "running", "attempt_id": "test-loop-R1-a0"},
        ])
        result = {"status": "complete", "commit": "abc123", "tests_passed": 5, "tests_total": 5}
        args = FakeArgs(state=str(state_path), unit="R99", attempt_id="whatever",
                         result=json.dumps(result))
        ret = cmd_record(args)
        assert ret == 3
        out = json.loads(capsys.readouterr().err)
        assert out["recorded"] is False
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["units"][0]["status"] == "running"  # untouched

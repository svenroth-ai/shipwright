"""Unit tests for ``lib.loop_mark`` (campaign-dag-scheduler R4): the
identity/token-checked "mark" half of R4's claim mechanics — ``mark-running``,
``mark-merged``, and the audited operator override ``mark``.

See sibling ``test_loop_claim.py`` for the "claim" half (ready-set/claim/
release). Same real-file-lock, mocked-subprocess convention.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from lib import loop_mark
from lib.loop_mark import _sanitize_text, cmd_mark, cmd_mark_merged, cmd_mark_running

_FAKE_SHA = "deadbeef" * 5
_OTHER_SHA = "cafebabe" * 5


def _write_state(tmp_path: Path, units: list[dict]) -> Path:
    state_path = tmp_path / ".shipwright" / "loop_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"loop_id": "test-loop", "kind": "sub_iterate", "units": units}),
                           encoding="utf-8")
    return state_path


def _unit_row(state_path: Path, unit_id: str) -> dict:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return next(u for u in state["units"] if u["id"] == unit_id)


class TestSanitizeText:
    def test_none_passes_through(self):
        assert _sanitize_text("x", None) is None

    def test_control_char_rejected(self):
        try:
            _sanitize_text("x", "hello\x00world")
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

    def test_over_length_rejected(self):
        try:
            _sanitize_text("x", "a" * 501)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

    def test_normal_text_returned_unchanged(self):
        assert _sanitize_text("x", "a reasonable reason") == "a reasonable reason"


def _mark_running_args(state_path: Path, unit: str, attempt_id: str) -> argparse.Namespace:
    return argparse.Namespace(state=str(state_path), unit=unit, attempt_id=attempt_id)


class TestCmdMarkRunning:
    def test_claimed_to_running_with_matching_token(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "claimed", "attempt_id": "l-A-a0"}])
        rc = cmd_mark_running(_mark_running_args(state_path, "A", "l-A-a0"))
        assert rc == 0
        assert _unit_row(state_path, "A")["status"] == "running"

    def test_stale_token_rejected(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "claimed", "attempt_id": "l-A-a0"}])
        assert cmd_mark_running(_mark_running_args(state_path, "A", "l-A-a1")) == 5

    def test_illegal_source_state_rejected(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "pending", "attempt_id": "l-A-a0"}])
        assert cmd_mark_running(_mark_running_args(state_path, "A", "l-A-a0")) == 1


def _mark_merged_args(state_path: Path, unit: str, attempt_id: str, merged_commit: str) -> argparse.Namespace:
    return argparse.Namespace(state=str(state_path), unit=unit, attempt_id=attempt_id,
                               merged_commit=merged_commit)


class TestCmdMarkMerged:
    def test_merging_to_merged_records_commit(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "merging", "attempt_id": "l-A-a0"}])
        rc = cmd_mark_merged(_mark_merged_args(state_path, "A", "l-A-a0", _FAKE_SHA))
        assert rc == 0
        row = _unit_row(state_path, "A")
        assert row["status"] == "merged"
        assert row["merged_commit"] == _FAKE_SHA

    def test_rejects_malformed_sha_before_any_write(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "merging", "attempt_id": "l-A-a0"}])
        assert cmd_mark_merged(_mark_merged_args(state_path, "A", "l-A-a0", "not-a-sha")) == 1
        assert _unit_row(state_path, "A")["status"] == "merging"  # untouched


def _mark_args(state_path: Path, unit: str, status: str, *, force=False, confirm=False,
                merged_commit=None, campaign_worktree=None, reason_code=None) -> argparse.Namespace:
    return argparse.Namespace(state=str(state_path), unit=unit, status=status, reason="operator says so",
                               operator="sven", reason_code=reason_code, merged_commit=merged_commit,
                               force=force, confirm_no_task_running=confirm,
                               campaign_worktree=campaign_worktree)


class TestCmdMark:
    def test_forced_edge_crossed_and_audited(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "failed"}])
        rc = cmd_mark(_mark_args(state_path, "A", "held"))
        assert rc == 0
        row = _unit_row(state_path, "A")
        assert row["status"] == "held"
        assert row["reason_code"] == "operator_mark"
        assert len(row["mark_audit"]) == 1 and row["mark_audit"][0]["from"] == "failed"

    def test_unknown_status_rejected(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "failed"}])
        assert cmd_mark(_mark_args(state_path, "A", "bogus")) == 1

    def test_running_requires_force_and_confirm(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "running"}])
        assert cmd_mark(_mark_args(state_path, "A", "held")) == 1
        assert cmd_mark(_mark_args(state_path, "A", "held", force=True)) == 1  # confirm missing too
        assert cmd_mark(_mark_args(state_path, "A", "held", force=True, confirm=True)) == 0

    def test_status_merged_requires_valid_merged_commit_arg(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "merging"}])
        assert cmd_mark(_mark_args(state_path, "A", "merged")) == 1
        assert cmd_mark(_mark_args(state_path, "A", "merged", merged_commit="nope")) == 1

    def test_status_merged_reverifies_ancestry_with_fresh_fetch(self, tmp_path):
        # "merging" is an ACTIVE state (a task may be running against it),
        # so it needs the same --force/--confirm-no-task-running gate as
        # "running" — merged is not exempt just because it's the happy path.
        state_path = _write_state(tmp_path, [{"id": "A", "status": "merging"}])
        with patch.object(loop_mark.subprocess, "run"), \
                patch.object(loop_mark, "fresh_remote_default_ref", return_value="origin/main"), \
                patch.object(loop_mark, "_is_ancestor", return_value=True):
            rc = cmd_mark(_mark_args(state_path, "A", "merged", merged_commit=_FAKE_SHA,
                                      campaign_worktree="/x", force=True, confirm=True))
        assert rc == 0
        assert _unit_row(state_path, "A")["merged_commit"] == _FAKE_SHA

    def test_status_merged_rejected_when_not_a_verified_ancestor(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "merging"}])
        with patch.object(loop_mark.subprocess, "run"), \
                patch.object(loop_mark, "fresh_remote_default_ref", return_value="origin/main"), \
                patch.object(loop_mark, "_is_ancestor", return_value=False):
            rc = cmd_mark(_mark_args(state_path, "A", "merged", merged_commit=_OTHER_SHA,
                                      campaign_worktree="/x", force=True, confirm=True))
        assert rc == 1
        assert _unit_row(state_path, "A")["status"] == "merging"  # untouched

    def test_status_merged_requires_campaign_worktree(self, tmp_path):
        """External code review (GLM, medium): the process cwd must never be
        an implicit fallback for the fetch/ancestry check `--status merged`
        performs — this is the one command most likely invoked by a human
        from an arbitrary directory."""
        state_path = _write_state(tmp_path, [{"id": "A", "status": "merging"}])
        rc = cmd_mark(_mark_args(state_path, "A", "merged", merged_commit=_FAKE_SHA,
                                  campaign_worktree=None, force=True, confirm=True))
        assert rc == 1
        assert _unit_row(state_path, "A")["status"] == "merging"  # untouched

    def test_sanitize_rejects_reason_with_control_char(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "failed"}])
        args = _mark_args(state_path, "A", "held")
        args.reason = "bad\x00reason"
        assert cmd_mark(args) == 1

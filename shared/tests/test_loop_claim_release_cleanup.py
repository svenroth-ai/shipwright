"""Unit tests for ``lib.loop_claim``'s ``cmd_release`` physical-cleanup half
(campaign-dag-scheduler R4, 2026-09-23 Stage-1 spec-reviewer re-check fix)
and the ADR-045 single-module-identity regression for ``mark``/
``mark-running``/``mark-merged`` dispatch. Split from ``test_loop_claim.py``
purely to keep each file under the 300-line guideline (same rationale as
the sibling ``test_loop_state_transitions.py``/``test_loop_state_fencing.py``
split) — no baseline implication, this file never existed before.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

from lib import loop_claim
from lib.loop_claim import cmd_release


def _write_state(tmp_path: Path, **overrides) -> Path:
    state_path = tmp_path / ".shipwright" / "loop_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "loop_id": "test-loop", "kind": "sub_iterate", "branch_strategy": "independent",
        "units": [{"id": "A", "status": "pending", "attempt": 0}],
    }
    state.update(overrides)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


def _release_args(state_path: Path, unit: str, attempt_id: str, *, max_attempts=3,
                   campaign_slug=None, campaign_worktree=None) -> argparse.Namespace:
    return argparse.Namespace(state=str(state_path), unit=unit, attempt_id=attempt_id,
                               max_attempts=max_attempts, campaign_slug=campaign_slug,
                               campaign_worktree=campaign_worktree)


class TestCmdReleasePhysicalCleanup:
    def test_release_skips_cleanup_without_campaign_context(self, tmp_path):
        """No `--campaign-slug`/`--campaign-worktree` (e.g. a caller that
        predates this fix) -> release still succeeds, no cleanup attempted."""
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "claimed", "attempt": 0, "attempt_id": "test-loop-A-a0"},
        ])
        with patch.object(loop_claim, "_cleanup_unit_worktree") as mocked:
            rc = cmd_release(_release_args(state_path, "A", "test-loop-A-a0"))
        assert rc == 0
        mocked.assert_not_called()

    def test_release_attempts_physical_cleanup_with_campaign_context(self, tmp_path):
        """With `--campaign-slug`/`--campaign-worktree` given, a successful
        release calls the recomputed-path cleanup with the POST-release
        attempt (never a stored path — recomputed from validated
        (slug, unit_id, attempt))."""
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "claimed", "attempt": 1, "attempt_id": "test-loop-A-a1"},
        ])
        with patch.object(loop_claim, "_cleanup_unit_worktree") as mocked:
            rc = cmd_release(_release_args(state_path, "A", "test-loop-A-a1",
                                            campaign_slug="dag-scheduler",
                                            campaign_worktree="/repo"))
        assert rc == 0
        mocked.assert_called_once_with("/repo", "dag-scheduler", "A", 1)

    def test_release_cleanup_failure_never_blocks_the_logical_release(self, tmp_path):
        """Even a bug inside the cleanup helper itself (not just an
        anticipated subprocess failure) must not surface as a non-zero
        `cmd_release` exit or prevent the state write that already
        happened — belt-and-suspenders around `_cleanup_unit_worktree`."""
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "claimed", "attempt": 0, "attempt_id": "test-loop-A-a0"},
        ])
        with patch.object(loop_claim, "_cleanup_unit_worktree", side_effect=OSError("locked")):
            rc = cmd_release(_release_args(state_path, "A", "test-loop-A-a0",
                                            campaign_slug="s", campaign_worktree="/repo"))
        assert rc == 0
        unit = json.loads(state_path.read_text(encoding="utf-8"))["units"][0]
        assert unit["status"] == "pending"

    def test_cleanup_unit_worktree_swallows_subprocess_failure(self, monkeypatch, tmp_path):
        """The real contract: `_cleanup_unit_worktree` itself never raises,
        even when the worktree exists and every git call fails (simulating a
        Windows file-lock still held by a just-exited runner process)."""
        from lib.loop_claim import _cleanup_unit_worktree

        fake_wt = tmp_path / "wt"
        fake_wt.mkdir()
        monkeypatch.setattr(loop_claim, "resolved_worktree_path", lambda *a, **k: fake_wt)

        def _boom(*a, **k):
            raise OSError("simulated Windows file lock")

        monkeypatch.setattr(loop_claim.subprocess, "run", _boom)
        _cleanup_unit_worktree("/repo", "dag-scheduler", "A", 0)  # must not raise

    def test_cleanup_unit_worktree_recomputes_path_never_trusts_a_stored_one(self, monkeypatch):
        """Security hardening: an invalid `(slug, unit_id)` recomputation
        must be refused, not silently accepted from caller-supplied data."""
        from lib.campaign_unit_worktree import CampaignUnitWorktreeError
        from lib.loop_claim import _cleanup_unit_worktree

        def _reject(*a, **k):
            raise CampaignUnitWorktreeError("invalid")

        monkeypatch.setattr(loop_claim, "resolved_worktree_path", _reject)
        _cleanup_unit_worktree("/repo", "bad slug", "A", 0)  # must not raise

    def test_cleanup_unit_worktree_noop_when_worktree_absent(self, monkeypatch, tmp_path):
        from lib.loop_claim import _cleanup_unit_worktree

        missing = tmp_path / "does-not-exist"
        monkeypatch.setattr(loop_claim, "resolved_worktree_path", lambda *a, **k: missing)
        with patch.object(loop_claim.subprocess, "run") as mocked:
            _cleanup_unit_worktree("/repo", "dag-scheduler", "A", 0)
        mocked.assert_not_called()


class TestMarkDispatchIsSingleModuleIdentity:
    """ADR-045 regression (Stage-1 spec-reviewer re-check, 2026-09-23):
    `loop_claim.py`'s `cmd_map` must dispatch into the SAME `lib.loop_mark`
    module object `test_loop_mark.py` patches — not a second, bare-imported
    copy with its own independent globals. A prior version of this file
    imported `from loop_mark import ...` (bare-sibling), a second, distinct
    module identity for the same file; a patch on `lib.loop_mark` would
    have silently had zero effect on that copy's functions."""

    def test_dispatch_names_are_the_lib_loop_mark_module_object(self):
        import lib.loop_mark as canonical

        assert loop_claim.cmd_mark_running is canonical.cmd_mark_running
        assert loop_claim.cmd_mark_merged is canonical.cmd_mark_merged
        assert loop_claim.cmd_mark is canonical.cmd_mark
        # Only ONE `loop_mark` identity ever loads — no bare-sibling
        # `loop_mark` entry alongside `lib.loop_mark` in `sys.modules`.
        assert "loop_mark" not in sys.modules or sys.modules["loop_mark"] is canonical

    def test_patching_lib_loop_mark_is_honored_through_main_dispatch(self, tmp_path, monkeypatch):
        """End-to-end proof, not just an identity assert: patch a function
        `cmd_mark_running` actually calls, invoke it through
        `loop_claim.main()`'s own `cmd_map`, and observe the patch take
        effect — exactly the path silently broken before the ADR-045 fix."""
        import lib.loop_mark as canonical

        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "claimed", "attempt": 0, "attempt_id": "test-loop-A-a0"},
        ])
        monkeypatch.setattr(canonical, "now_iso", lambda: "PATCHED-TIMESTAMP")
        monkeypatch.setattr(sys, "argv", [
            "loop_claim.py", "mark-running", "--state", str(state_path),
            "--unit", "A", "--attempt-id", "test-loop-A-a0",
        ])
        rc = loop_claim.main()
        assert rc == 0
        unit = json.loads(state_path.read_text(encoding="utf-8"))["units"][0]
        assert unit["running_at"] == "PATCHED-TIMESTAMP"

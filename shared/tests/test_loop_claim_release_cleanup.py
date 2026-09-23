"""Unit tests for ``lib.loop_claim``'s ``cmd_release``: its ``--max-attempts``
argument validation, its basic status transitions, and its physical-cleanup
half (campaign-dag-scheduler R4, 2026-09-23 Stage-1 spec-reviewer re-check
fix). The ADR-045 single-module-identity regression for ``mark``/
``mark-running``/``mark-merged`` dispatch moved out to the sibling
``test_loop_claim_mark_dispatch.py`` (round 12). Split from
``test_loop_claim.py`` purely to keep each file under the 300-line
guideline (same rationale as the sibling ``test_loop_state_transitions.py``/
``test_loop_state_fencing.py`` split) — no baseline implication, this file
never existed before.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lib import loop_claim
from lib.campaign_unit_worktree import resolved_worktree_path
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


class TestCmdRelease:
    """Basic ``cmd_release`` status transitions — moved from
    ``test_loop_claim.py`` (round 10) purely to keep that file under the
    300-line guideline after its `cmd_next_batch` kind-recheck regression
    test; this file already owns the `cmd_release` cleanup-half tests
    below, so it's the natural home for the rest of `cmd_release` too."""

    def test_rejects_zero_max_attempts_instead_of_failing_every_release(self, tmp_path):
        """External Tier-3 PR review (GPT, round 12): `unit.get("attempt",
        0) + 1 >= args.max_attempts` is trivially true for `max_attempts <=
        0` (attempt is always >= 0), so an unvalidated zero/negative value
        would silently mark a unit `failed` on its very first release, with
        no valid attempt budget ever having existed. Must be rejected up
        front, before the lock is even acquired, and the unit left
        untouched."""
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "claimed", "attempt": 0, "attempt_id": "test-loop-A-a0"},
        ])
        rc = cmd_release(_release_args(state_path, "A", "test-loop-A-a0", max_attempts=0))
        assert rc == 1
        unit = json.loads(state_path.read_text(encoding="utf-8"))["units"][0]
        assert unit["status"] == "claimed"  # untouched

    def test_rejects_negative_max_attempts(self, tmp_path):
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "claimed", "attempt": 0, "attempt_id": "test-loop-A-a0"},
        ])
        rc = cmd_release(_release_args(state_path, "A", "test-loop-A-a0", max_attempts=-1))
        assert rc == 1
        unit = json.loads(state_path.read_text(encoding="utf-8"))["units"][0]
        assert unit["status"] == "claimed"  # untouched

    def test_release_returns_to_pending_without_bumping_attempt(self, tmp_path):
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "claimed", "attempt": 0, "attempt_id": "test-loop-A-a0"},
        ])
        rc = cmd_release(_release_args(state_path, "A", "test-loop-A-a0"))
        assert rc == 0
        unit = json.loads(state_path.read_text(encoding="utf-8"))["units"][0]
        assert unit["status"] == "pending"
        assert unit["attempt"] == 0  # release itself never bumps

    def test_release_fails_to_failed_once_max_attempts_exhausted(self, tmp_path):
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "claimed", "attempt": 2, "attempt_id": "test-loop-A-a2"},
        ])
        rc = cmd_release(_release_args(state_path, "A", "test-loop-A-a2", max_attempts=3))
        assert rc == 0
        unit = json.loads(state_path.read_text(encoding="utf-8"))["units"][0]
        assert unit["status"] == "failed"

    def test_release_rejects_stale_attempt_token(self, tmp_path):
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "claimed", "attempt": 1, "attempt_id": "test-loop-A-a1"},
        ])
        assert cmd_release(_release_args(state_path, "A", "test-loop-A-a0")) == 5

    def test_release_rejects_non_claimed_unit(self, tmp_path):
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "running", "attempt": 0, "attempt_id": "test-loop-A-a0"},
        ])
        assert cmd_release(_release_args(state_path, "A", "test-loop-A-a0")) == 1

    def test_release_unknown_unit_returns_1(self, tmp_path):
        state_path = _write_state(tmp_path)
        assert cmd_release(_release_args(state_path, "missing", "x")) == 1


class TestCmdReleasePhysicalCleanup:
    def test_release_rejects_non_sub_iterate_kind(self, tmp_path):
        """External review (GPT, high): this module's own docstring promises
        it NEVER touches `kind == "section"` state — unlike `cmd_next_batch`,
        `cmd_release` had no gate enforcing that before this fix, so a wrong
        `--state` path could write the 9-state vocabulary into a legacy
        section row."""
        state_path = _write_state(tmp_path, kind="section", units=[
            {"id": "A", "status": "in_progress"},
        ])
        assert cmd_release(_release_args(state_path, "A", "whatever")) == 1
        unit = json.loads(state_path.read_text(encoding="utf-8"))["units"][0]
        assert unit["status"] == "in_progress"  # untouched

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

    def test_release_cleanup_uses_canonical_unit_id_not_caller_casing(self, tmp_path):
        """External Tier-3 PR review (GPT, round 17): `find_unit_row`
        resolves a case-mismatched `--unit` via its case-folded fallback and
        the logical release correctly mutates the matched row, but the
        pre-fix code then passed the CALLER's raw spelling straight through
        to `_cleanup_unit_worktree`, which RECOMPUTES the worktree path from
        that string — a case mismatch silently no-ops cleanup on any
        case-sensitive filesystem (Linux CI), leaving the real worktree and
        branch behind with no error at all (best-effort, never blocking).
        Must use the canonical `unit["id"]`, not `args.unit`."""
        state_path = _write_state(tmp_path, units=[
            {"id": "R4", "status": "claimed", "attempt": 0, "attempt_id": "test-loop-R4-a0"},
        ])
        with patch.object(loop_claim, "_cleanup_unit_worktree") as mocked:
            rc = cmd_release(_release_args(state_path, "r4", "test-loop-R4-a0",
                                            campaign_slug="dag-scheduler",
                                            campaign_worktree="/repo"))
        assert rc == 0
        mocked.assert_called_once_with("/repo", "dag-scheduler", "R4", 0)

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
        monkeypatch.setattr(loop_claim, "main_repo_root", lambda p: tmp_path)
        monkeypatch.setattr(loop_claim, "resolved_worktree_path", lambda *a, **k: fake_wt)

        def _boom(*a, **k):
            raise OSError("simulated Windows file lock")

        monkeypatch.setattr(loop_claim.subprocess, "run", _boom)
        _cleanup_unit_worktree("/repo", "dag-scheduler", "A", 0)  # must not raise

    def test_cleanup_unit_worktree_recomputes_path_never_trusts_a_stored_one(self, monkeypatch, tmp_path):
        """Security hardening: an invalid `(slug, unit_id)` recomputation
        must be refused, not silently accepted from caller-supplied data."""
        from lib.campaign_unit_worktree import CampaignUnitWorktreeError
        from lib.loop_claim import _cleanup_unit_worktree

        def _reject(*a, **k):
            raise CampaignUnitWorktreeError("invalid")

        monkeypatch.setattr(loop_claim, "main_repo_root", lambda p: tmp_path)
        monkeypatch.setattr(loop_claim, "resolved_worktree_path", _reject)
        _cleanup_unit_worktree("/repo", "bad slug", "A", 0)  # must not raise

    def test_cleanup_unit_worktree_noop_when_worktree_absent(self, monkeypatch, tmp_path):
        from lib.loop_claim import _cleanup_unit_worktree

        missing = tmp_path / "does-not-exist"
        monkeypatch.setattr(loop_claim, "main_repo_root", lambda p: tmp_path)
        monkeypatch.setattr(loop_claim, "resolved_worktree_path", lambda *a, **k: missing)
        with patch.object(loop_claim.subprocess, "run") as mocked:
            _cleanup_unit_worktree("/repo", "dag-scheduler", "A", 0)
        mocked.assert_not_called()

    def test_cleanup_unit_worktree_real_git_calls_fire_against_the_correct_path(self, tmp_path):
        """Stage-3 doubt review (HIGH #4), REAL (non-mocked) regression: all 5
        tests above patch `resolved_worktree_path` away entirely, so none of
        them would have caught the path-doubling bug (`campaign_worktree` --
        which is ALREADY `<main_root>/.worktrees/campaign-{slug}` --
        passed as `resolved_worktree_path`'s `main_root` argument, computing
        a doubled, nonexistent path that always hit the `exists()` guard and
        silently no-op'd). This test builds an ACTUAL git repo with an actual
        campaign worktree AND an actual per-unit worktree on disk, calls
        `_cleanup_unit_worktree` with the real `campaign_worktree` shape a
        production caller passes, and asserts the per-unit worktree is
        genuinely gone afterwards -- proof the real git calls fired against
        the correctly-recomputed path, not a mock."""
        if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
            pytest.skip("git not available")

        main_root = tmp_path / "main"
        main_root.mkdir()

        def run(*args):
            return subprocess.run(
                ["git", *args], cwd=main_root, capture_output=True, text=True, timeout=30)

        run("init", "-q")
        run("config", "user.email", "test@example.com")
        run("config", "user.name", "Test")
        (main_root / "README.md").write_text("x", encoding="utf-8")
        run("add", "README.md")
        run("commit", "-q", "-m", "initial")

        campaign_slug = "dag-scheduler"
        unit_id = "A"
        attempt = 0

        # The CAMPAIGN-level worktree -- what `cmd_release` actually passes as
        # `campaign_worktree` (already inside `.worktrees/`, per
        # `campaign_unit_worktree.py`'s own docs).
        campaign_wt_path = main_root / ".worktrees" / f"campaign-{campaign_slug}"
        result = run("worktree", "add", "-q", str(campaign_wt_path), "-b", "campaign-branch")
        assert result.returncode == 0, result.stderr

        # The PER-UNIT worktree `_cleanup_unit_worktree` must locate and remove.
        unit_wt_path = resolved_worktree_path(main_root, campaign_slug, unit_id, attempt=attempt)
        result = run("worktree", "add", "-q", str(unit_wt_path), "-b", "unit-branch")
        assert result.returncode == 0, result.stderr
        assert unit_wt_path.exists()

        from lib.loop_claim import _cleanup_unit_worktree

        _cleanup_unit_worktree(str(campaign_wt_path), campaign_slug, unit_id, attempt)

        assert not unit_wt_path.exists(), (
            "the per-unit worktree must actually be removed by a real `git "
            "worktree remove` -- if this still exists, the path arithmetic "
            "silently no-op'd again"
        )
        # And the branch it had checked out is gone too (best-effort branch -D).
        branches = run("branch", "--list", "unit-branch").stdout
        assert "unit-branch" not in branches

    # The ADR-045 single-module-identity regression for `mark`/
    # `mark-running`/`mark-merged` dispatch lives in the sibling
    # `test_loop_claim_mark_dispatch.py` (moved out round 12, purely to
    # keep this file under the 300-line guideline — it was never about
    # `cmd_release` in the first place).

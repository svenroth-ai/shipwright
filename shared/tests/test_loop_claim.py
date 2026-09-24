"""Unit tests for ``lib.loop_claim`` (campaign-dag-scheduler R4): the
ready-set/claim/release "claim" half. ``mark``/``mark-running``/
``mark-merged`` (the "identity" half, split into ``lib.loop_mark``) are
covered in the sibling ``test_loop_mark.py``.

Every scenario calls the ``cmd_*`` functions directly with a real
``argparse.Namespace`` and a real on-disk state file under ``tmp_path`` —
``file_lock`` is real (single-process, uncontended) so the atomic-write path
is exercised, not mocked away. Only ``subprocess.run`` (git) is mocked.
"""

from __future__ import annotations

from unittest.mock import patch

from lib import loop_claim
from lib.loop_claim import (
    _ancestry_ok,
    _claim_unit,
    _resolve_batch_base,
)

_FAKE_SHA = "deadbeef" * 5


class TestClaimUnit:
    def test_first_claim_never_bumps_attempt(self):
        unit = {"id": "A", "status": "pending", "attempt": 0}
        attempt, attempt_id = _claim_unit(unit, "loop1")
        assert attempt == 0
        assert attempt_id == "loop1-A-a0"
        assert unit["status"] == "claimed"

    def test_reclaim_bumps_attempt_exactly_once(self):
        # attempt_id present => this unit was claimed at least once before.
        unit = {"id": "A", "status": "pending", "attempt": 0, "attempt_id": "loop1-A-a0"}
        attempt, attempt_id = _claim_unit(unit, "loop1")
        assert attempt == 1
        assert attempt_id == "loop1-A-a1"

    def test_claim_writes_an_initial_lease_so_unit_is_never_never_leased(self):
        """External code review (GLM, medium): without a claim-time lease
        start, a just-claimed unit reads as "never leased" and a reconcile
        in that window would burn an attempt before the runner's first
        real heartbeat lands."""
        import time as _time
        unit = {"id": "A", "status": "pending", "attempt": 0}
        before = _time.time()
        _claim_unit(unit, "loop1")
        assert "lease_expires_at" in unit
        assert unit["lease_expires_at"] > before


class TestResolveBatchBase:
    def test_serial_uses_fresh_remote_default_ref(self, monkeypatch):
        monkeypatch.setattr(loop_claim, "fresh_remote_default_ref", lambda cwd=None: "origin/main")
        assert _resolve_batch_base("serial", cwd="/x") == "origin/main"

    def test_independent_is_main(self):
        assert _resolve_batch_base("independent", cwd="/x") == "main"

    def test_stacked_and_unknown_resolve_to_none(self):
        assert _resolve_batch_base("stacked", cwd="/x") is None
        assert _resolve_batch_base("bogus", cwd="/x") is None


class TestAncestryOk:
    def test_no_deps_is_always_ok(self):
        assert _ancestry_ok({"depends_on": []}, [], "main") is True
        assert _ancestry_ok({}, [], "main") is True

    def test_deps_present_but_no_base_branch_fails_closed(self):
        assert _ancestry_ok({"depends_on": ["A"]}, [{"id": "A"}], None) is False

    def test_dep_missing_merged_commit_fails(self):
        all_units = [{"id": "A", "status": "pending"}]  # never merged
        assert _ancestry_ok({"depends_on": ["A"]}, all_units, "main") is False

    def test_dep_invalid_sha_fails(self):
        all_units = [{"id": "A", "merged_commit": "not-a-sha"}]
        assert _ancestry_ok({"depends_on": ["A"]}, all_units, "main") is False

    def test_ancestor_confirmed_without_fetch(self):
        all_units = [{"id": "A", "merged_commit": _FAKE_SHA}]
        with patch.object(loop_claim, "_is_ancestor", return_value=True) as mocked:
            assert _ancestry_ok({"depends_on": ["A"]}, all_units, "main") is True
        mocked.assert_called_once()

    def test_ancestor_confirmed_after_one_fetch_retry(self):
        all_units = [{"id": "A", "merged_commit": _FAKE_SHA}]
        with patch.object(loop_claim, "_is_ancestor", side_effect=[False, True]), \
                patch.object(loop_claim.subprocess, "run") as mocked_fetch:
            assert _ancestry_ok({"depends_on": ["A"]}, all_units, "main") is True
        mocked_fetch.assert_called_once()

    def test_still_absent_after_fetch_leaves_unit_pending_for_next_round(self):
        all_units = [{"id": "A", "merged_commit": _FAKE_SHA}]
        with patch.object(loop_claim, "_is_ancestor", return_value=False), \
                patch.object(loop_claim.subprocess, "run"):
            assert _ancestry_ok({"depends_on": ["A"]}, all_units, "main") is False


# `cmd_next_batch` (outside-lock/locked-reload race handling, ready-set
# computation) is covered in the sibling `test_loop_claim_next_batch.py`.
# `cmd_release`'s basic status transitions, its physical-cleanup behavior
# (`--campaign-slug`/`--campaign-worktree`, `_cleanup_unit_worktree`), and
# the ADR-045 single-module-identity regression for
# `mark`/`mark-running`/`mark-merged` dispatch are covered in the sibling
# `test_loop_claim_release_cleanup.py`. Both split out purely to keep this
# file under the 300-line guideline.

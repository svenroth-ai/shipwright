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

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from lib import loop_claim
from lib.loop_claim import (
    MAX_PARALLEL_HARD_CAP,
    _ancestry_ok,
    _claim_unit,
    _resolve_batch_base,
    cmd_next_batch,
    cmd_release,
)

_FAKE_SHA = "deadbeef" * 5


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


def _batch_args(state_path: Path, *, max_parallel=2, campaign_worktree=None) -> argparse.Namespace:
    return argparse.Namespace(state=str(state_path), max_parallel=max_parallel,
                               campaign_worktree=campaign_worktree)


class TestCmdNextBatch:
    def test_rejects_invalid_max_parallel(self, tmp_path):
        state_path = _write_state(tmp_path)
        assert cmd_next_batch(_batch_args(state_path, max_parallel=0)) == 1
        assert cmd_next_batch(_batch_args(state_path, max_parallel=MAX_PARALLEL_HARD_CAP + 1)) == 1

    def test_rejects_non_sub_iterate_kind(self, tmp_path):
        state_path = _write_state(tmp_path, kind="section")
        assert cmd_next_batch(_batch_args(state_path)) == 1

    def test_claims_ready_units_up_to_max_parallel(self, tmp_path, capsys):
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "pending", "attempt": 0},
            {"id": "B", "status": "pending", "attempt": 0},
            {"id": "C", "status": "pending", "attempt": 0},
        ])
        rc = cmd_next_batch(_batch_args(state_path, max_parallel=2))
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert [c["id"] for c in out["claimed"]] == ["A", "B"]
        state = json.loads(state_path.read_text(encoding="utf-8"))
        statuses = {u["id"]: u["status"] for u in state["units"]}
        assert statuses == {"A": "claimed", "B": "claimed", "C": "pending"}

    def test_claims_unit_whose_dependency_ancestry_verifies(self, tmp_path, capsys):
        """External code review (GLM, low): a `cmd_next_batch`-level test
        with a real `depends_on` edge, closing the gap where only
        `_ancestry_ok` in isolation and dependency-free units were covered
        — a wrong `cwd`/skipped ancestry-check wiring bug would still pass
        every other test here."""
        state_path = _write_state(tmp_path, units=[
            {"id": "dep", "status": "merged", "attempt": 0, "merged_commit": _FAKE_SHA},
            {"id": "A", "status": "pending", "attempt": 0, "depends_on": ["dep"]},
        ])
        with patch.object(loop_claim, "_is_ancestor", return_value=True), \
                patch.object(loop_claim.subprocess, "run"):
            rc = cmd_next_batch(_batch_args(state_path, max_parallel=1))
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert [c["id"] for c in out["claimed"]] == ["A"]

    def test_claims_unit_whose_dependency_id_is_case_mismatched(self, tmp_path, capsys):
        """`campaign_graph.validate_dependency_graph` accepts a
        case-mismatched `depends_on` edge at write time (e.g.
        `depends_on: ["r0"]` against unit `R0`) — the happy path (SHA
        unchanged between peek and claim) must still claim the unit."""
        state_path = _write_state(tmp_path, units=[
            {"id": "R0", "status": "merged", "attempt": 0, "merged_commit": _FAKE_SHA},
            {"id": "A", "status": "pending", "attempt": 0, "depends_on": ["r0"]},
        ])
        with patch.object(loop_claim, "_is_ancestor", return_value=True), \
                patch.object(loop_claim.subprocess, "run"):
            rc = cmd_next_batch(_batch_args(state_path, max_parallel=1))
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert [c["id"] for c in out["claimed"]] == ["A"]

    def test_case_mismatched_dependency_staleness_is_still_detected(self, tmp_path, capsys):
        """Stage-2 code review (medium, correctness): `_snapshot_merged_commits`
        used to key its `{unit_id: merged_commit}` map by exact-case
        `u["id"]`, while the comparison site looked up `dep_id` from
        `depends_on` raw. For a case-mismatched edge (`depends_on: ["r0"]`
        against unit `R0`), BOTH the pre- and in-lock snapshots returned
        `None` for that key, so the "did this dependency's merged SHA
        change between the outside-lock peek and the in-lock claim" check
        passed VACUOUSLY — the happy-path test above cannot tell this apart
        from a correct fold, since a vacuous `None == None` also claims the
        unit. This test forces the dependency's `merged_commit` to actually
        change between the two reads `cmd_next_batch` performs (outside-lock
        peek, in-lock re-read) and asserts the unit is correctly EXCLUDED —
        the case-fold fix is what makes that comparison a real one."""
        state_path = _write_state(tmp_path, units=[
            {"id": "R0", "status": "merged", "attempt": 0, "merged_commit": _FAKE_SHA},
            {"id": "A", "status": "pending", "attempt": 0, "depends_on": ["r0"]},
        ])
        stale_state = json.loads(state_path.read_text(encoding="utf-8"))
        changed_state = json.loads(json.dumps(stale_state))
        changed_state["units"][0]["merged_commit"] = "cafebabe" * 5  # different SHA, in-lock

        with patch.object(loop_claim, "_load_state", side_effect=[stale_state, changed_state]), \
                patch.object(loop_claim, "_is_ancestor", return_value=True), \
                patch.object(loop_claim.subprocess, "run"):
            rc = cmd_next_batch(_batch_args(state_path, max_parallel=1))
        out = json.loads(capsys.readouterr().out)
        assert out["claimed"] == []
        assert rc == 4

    def test_all_terminal_reports_done(self, tmp_path):
        state_path = _write_state(tmp_path, units=[{"id": "A", "status": "merged", "attempt": 0}])
        assert cmd_next_batch(_batch_args(state_path)) == 2

    def test_stalled_batch_reports_blockers(self, tmp_path, capsys):
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "pending", "attempt": 0, "depends_on": ["B"]},
            {"id": "B", "status": "running", "attempt": 0},
        ])
        rc = cmd_next_batch(_batch_args(state_path))
        assert rc == 4
        out = json.loads(capsys.readouterr().out)
        assert out["blocked_pending_ids"] == ["A"]

    def test_lock_timeout_returns_6(self, tmp_path):
        state_path = _write_state(tmp_path)
        with patch.object(loop_claim, "file_lock", side_effect=loop_claim.LockTimeout("busy")):
            assert cmd_next_batch(_batch_args(state_path)) == 6


def _release_args(state_path: Path, unit: str, attempt_id: str, *, max_attempts=3,
                   campaign_slug=None, campaign_worktree=None) -> argparse.Namespace:
    return argparse.Namespace(state=str(state_path), unit=unit, attempt_id=attempt_id,
                               max_attempts=max_attempts, campaign_slug=campaign_slug,
                               campaign_worktree=campaign_worktree)


class TestCmdRelease:
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

    # `cmd_release`'s physical-cleanup behavior (`--campaign-slug`/
    # `--campaign-worktree`, `_cleanup_unit_worktree`) and the ADR-045
    # single-module-identity regression for `mark`/`mark-running`/
    # `mark-merged` dispatch are covered in the sibling
    # `test_loop_claim_release_cleanup.py`, split out purely to keep this
    # file under the 300-line guideline.

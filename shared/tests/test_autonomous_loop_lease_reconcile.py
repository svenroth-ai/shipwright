"""Regression tests: `kind == "section"`'s legacy `_reconcile_in_progress`
salvage path (result.json fast path, branch-has-commits guess, reset-to-
pending fallback) survives R4's move into `lib.loop_state.reconcile_in_progress`
byte-identical.

Campaign campaign-dag-scheduler R2, Stage-2 code review (high) + doubt-review
(high, on the first fix attempt): `lib.unit_lease.touch_unit_lease` writes
`branch` onto a unit's row from Step 1 (before any commit), which made
`_reconcile_in_progress`'s branch-has-commits heuristic reachable for a
genuinely still-running unit on any campaign-session resume, silently
marking it falsely `complete` with no `result.json`. The fix (gate on
PROVENANCE — a lease-touched row's `branch` never implies `cmd_record`
reported back) is preserved here.

**R4 retarget (campaign-dag-scheduler R4):** this suite originally exercised
`kind: "sub_iterate"` rows against the SHARED pre-R4 function — but that
function never actually branched on `kind` at all, so these scenarios were
really testing the mechanism `kind == "section"` still uses verbatim today
(a `kind == "sub_iterate"` row now takes an entirely different,
lease-expiry-only path — see `test_loop_state_transitions.py::TestReconcileLeases`
for ITS coverage). Retargeted to `kind: "section"`, the kind this exact
code path now actually serves; every scenario body is unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from lib.loop_state import reconcile_in_progress  # noqa: E402


def _in_progress_unit(**overrides) -> dict:
    unit = {
        "id": "R2",
        "status": "in_progress",
        "attempt": 0,
        "started_at": "2026-09-22T05:00:00Z",
        "finished_at": None,
        "commit": None,
        "head_sha": "abc123",
        "branch": "iterate/campaign-r2-worktree-capability",
        "result_path": None,
        "handoff_path": None,
        "failure_reason": None,
    }
    unit.update(overrides)
    return unit


def _state_with(unit: dict) -> dict:
    return {"loop_id": "test-loop", "kind": "section", "units": [unit]}


@pytest.fixture(autouse=True)
def _cwd_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _state_path(tmp_path) -> Path:
    return tmp_path / ".shipwright" / "loop_state.json"


def _mock_git_shows_commits_since_head_sha(*args, **kwargs):
    cmd = args[0]
    if cmd[:3] == ["git", "rev-parse", "--verify"]:
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    if cmd[:2] == ["git", "log"]:
        return type("R", (), {"returncode": 0, "stdout": "deadbeef a commit\n", "stderr": ""})()
    raise AssertionError(f"unexpected subprocess call: {cmd}")


class TestLeaseAwareReconcile:
    def test_a_live_lease_still_resets_to_pending_not_falsely_complete(self, tmp_path):
        """A live lease must NOT be read as evidence of completion — the
        branch-has-commits guess never applies once a row has been
        lease-touched, so it falls through to the pending-reset instead."""
        unit = _in_progress_unit(lease_touched_at=1_000_000_000.0, lease_expires_at=9_999_999_999.0)
        state = _state_with(unit)
        with patch("lib.loop_state.subprocess.run", side_effect=_mock_git_shows_commits_since_head_sha):
            warnings = reconcile_in_progress(state, "section", _state_path(tmp_path))
        assert unit["status"] == "pending"
        assert unit["attempt"] == 1
        assert any("reset to pending" in w for w in warnings)

    def test_a_stale_lease_also_resets_to_pending_not_falsely_complete(self, tmp_path):
        """The doubt-reviewer's exact disproof scenario: a resume happening
        AFTER the lease has expired must not fall back to the
        branch-has-commits guess either — it is the common resume case, not
        the exotic one, and gating on staleness alone re-triggered the bug."""
        unit = _in_progress_unit(lease_touched_at=1.0, lease_expires_at=1.0)  # long expired
        state = _state_with(unit)
        with patch("lib.loop_state.subprocess.run", side_effect=_mock_git_shows_commits_since_head_sha):
            warnings = reconcile_in_progress(state, "section", _state_path(tmp_path))
        assert unit["status"] == "pending"
        assert unit["attempt"] == 1
        assert any("reset to pending" in w for w in warnings)

    def test_no_lease_fields_at_all_falls_through_unchanged(self, tmp_path):
        """A unit that was never touched (pre-R2 campaign, or R2 code not yet
        reached Step 1) has no `lease_touched_at` — behavior is byte-identical
        to before this fix: the branch-has-commits guess still applies."""
        unit = _in_progress_unit()
        assert "lease_touched_at" not in unit
        state = _state_with(unit)
        with patch("lib.loop_state.subprocess.run", side_effect=_mock_git_shows_commits_since_head_sha):
            warnings = reconcile_in_progress(state, "section", _state_path(tmp_path))
        assert unit["status"] == "complete"
        assert any("branch has commits" in w for w in warnings)

    def test_no_lease_fields_and_no_evidence_resets_to_pending(self, tmp_path):
        unit = _in_progress_unit(branch=None)
        state = _state_with(unit)
        warnings = reconcile_in_progress(state, "section", _state_path(tmp_path))
        assert unit["status"] == "pending"
        assert unit["attempt"] == 1
        assert any("reset to pending" in w for w in warnings)

    def test_a_result_json_complete_unit_is_reconciled_regardless_of_lease(self, tmp_path):
        """The result.json fast path stays first and unconditional — a
        genuinely finished unit is reconciled the same way no matter what
        lease fields it carries."""
        unit = _in_progress_unit(lease_touched_at=1_000_000_000.0, lease_expires_at=9_999_999_999.0)
        state = _state_with(unit)
        runs_dir = tmp_path / ".shipwright" / "runs" / "test-loop" / "R2"
        runs_dir.mkdir(parents=True)
        (runs_dir / "result.json").write_text('{"status": "complete", "commit": "abc123"}',
                                                encoding="utf-8")
        warnings = reconcile_in_progress(state, "section", _state_path(tmp_path))
        assert unit["status"] == "complete"
        assert unit["commit"] == "abc123"
        assert any("found result.json" in w for w in warnings)

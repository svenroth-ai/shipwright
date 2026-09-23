"""Unit tests for ``lib.loop_claim.cmd_next_batch`` (campaign-dag-scheduler
R4/R20) — the batch-claim command's outside-lock/locked-reload race
handling and ready-set computation.

Split out of the sibling ``test_loop_claim.py`` purely to keep both files
under the repo's 300-line guideline — no baseline implication, this file
never existed before.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from lib import loop_claim
from lib.loop_claim import MAX_PARALLEL_HARD_CAP, cmd_next_batch

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

    def test_recheck_kind_after_lock_prevents_a_section_state_race(self, tmp_path, capsys):
        """External Tier-3 PR review (GPT, round 10): the outside-lock peek
        validates `kind` before `loop.lock` is acquired; a concurrent
        `cmd_init` can replace the state file with a `kind == "section"`
        one in that window. `cmd_next_batch` must re-check `kind` on the
        locked reload too, before any unit is inspected or mutated, so its
        documented guarantee (module docstring: NEVER touches
        `kind == "section"` state) holds under the race, not just on the
        initial read."""
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "pending", "attempt": 0},
        ])
        sub_iterate_state = json.loads(state_path.read_text(encoding="utf-8"))
        section_state = json.loads(json.dumps(sub_iterate_state))
        section_state["kind"] = "section"

        with patch.object(loop_claim, "_load_state", side_effect=[sub_iterate_state, section_state]):
            rc = cmd_next_batch(_batch_args(state_path, max_parallel=1))
        assert rc == 1
        assert "sub_iterate" in capsys.readouterr().err
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["units"][0]["status"] == "pending"

    def test_recheck_branch_strategy_after_lock_prevents_a_stale_base_branch_race(self, tmp_path, capsys):
        """External Tier-3 PR review (GPT, PR #790 round 20): `base_branch`
        (and everything derived from it outside the lock: `ancestry_confirmed`,
        `pre_snapshot`, `pre_depends_on`) is resolved from `branch_strategy` on
        the UNLOCKED peek — the same race window round 10 closed for `kind`
        was left open for `branch_strategy`. A concurrent `cmd_init` that
        re-runs the same `loop_id` with a different `branch_strategy` in that
        window must not let this call proceed and tag units with the now-stale
        `base_branch`; it must fail closed instead, exactly like the `kind`
        race does."""
        state_path = _write_state(tmp_path, branch_strategy="independent", units=[
            {"id": "A", "status": "pending", "attempt": 0},
        ])
        peeked_state = json.loads(state_path.read_text(encoding="utf-8"))
        locked_state = json.loads(json.dumps(peeked_state))
        locked_state["branch_strategy"] = "serial"  # changed under the lock

        with patch.object(loop_claim, "_load_state", side_effect=[peeked_state, locked_state]):
            rc = cmd_next_batch(_batch_args(state_path, max_parallel=1))
        assert rc == 1
        assert "branch_strategy" in capsys.readouterr().err
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["units"][0]["status"] == "pending"

    def test_rejects_stacked_strategy_before_claiming_instead_of_null_base(self, tmp_path, capsys):
        """External Tier-3 PR review (GPT, round 6): `"stacked"` (and any
        other strategy `_resolve_batch_base` can't resolve) must never reach
        the ready-set computation — a dependency-free unit would otherwise be
        silently claimed with `"base_branch": null` while a dependency-bearing
        unit stalls forever with no error explaining why."""
        state_path = _write_state(tmp_path, branch_strategy="stacked", units=[
            {"id": "A", "status": "pending", "attempt": 0},
        ])
        assert cmd_next_batch(_batch_args(state_path)) == 1
        assert "stacked" in capsys.readouterr().err
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["units"][0]["status"] == "pending"

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

    def test_new_dependency_added_between_peek_and_lock_is_not_trusted(self, tmp_path, capsys):
        """External Tier-3 PR review (GPT, round 11): `ancestry_confirmed` is
        computed from the peek-time `depends_on` edge set; a concurrent
        writer that ADDS a brand-new edge to an already-`pending` unit
        between the peek and the locked reload is invisible to the SHA-
        staleness check alone whenever the new dependency was ALREADY merged
        before the peek and its `merged_commit` never changes in that same
        window — the snapshot comparison passes vacuously for an edge it
        never even looked at. Here `A` has no deps at peek time (trivially
        `ancestry_confirmed`), then gains `depends_on: ["B"]` before the lock
        is acquired, where `B` was already merged beforehand and stays that
        way — the edge-set check must still exclude `A` this round, since
        `_ancestry_ok` never verified `B`'s ancestry for `A` at all."""
        state_path = _write_state(tmp_path, units=[
            {"id": "A", "status": "pending", "attempt": 0},
            {"id": "B", "status": "merged", "attempt": 0, "merged_commit": _FAKE_SHA},
        ])
        peeked_state = json.loads(state_path.read_text(encoding="utf-8"))
        locked_state = json.loads(json.dumps(peeked_state))
        locked_state["units"][0]["depends_on"] = ["B"]  # added after the peek

        with patch.object(loop_claim, "_load_state", side_effect=[peeked_state, locked_state]):
            rc = cmd_next_batch(_batch_args(state_path, max_parallel=1))
        out = json.loads(capsys.readouterr().out)
        assert out["claimed"] == []
        assert rc == 4

    def test_lock_timeout_returns_6(self, tmp_path):
        state_path = _write_state(tmp_path)
        with patch.object(loop_claim, "file_lock", side_effect=loop_claim.LockTimeout("busy")):
            assert cmd_next_batch(_batch_args(state_path)) == 6

    # `cmd_release`'s basic status transitions, its physical-cleanup
    # behavior (`--campaign-slug`/`--campaign-worktree`,
    # `_cleanup_unit_worktree`), and the ADR-045 single-module-identity
    # regression for `mark`/`mark-running`/`mark-merged` dispatch are all
    # covered in the sibling `test_loop_claim_release_cleanup.py`, split
    # out purely to keep this file under the 300-line guideline.

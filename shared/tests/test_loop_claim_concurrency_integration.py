"""Integration test (``category: "integration"``) for
``lib.loop_claim``/``lib.loop_state`` (campaign-dag-scheduler R4's own "Test
strategy" section): N concurrent claims against a shared ``loop_state.json``
from SEPARATE OS PROCESSES with REAL file locking (never mocked here — the
mocked equivalents live in ``test_loop_claim.py``/``test_loop_state_transitions.py``
for the diff-coverage gate, per the same section's explicit pairing
instruction), lease expiry/reclaim at a simulated wave boundary, and the
dependency-ancestry assert correctly leaving a claim ``pending`` (never
crashing the whole batch) when the local repository cannot prove a
dependency is actually merged.

Lives under ``shared/tests`` (one-test-root-per-process rule), matching the
placement rationale of every other R2/R4 integration test in this campaign
(``test_r2_worktree_capability_integration.py``,
``test_campaign_dag_integration.py``).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lib.unit_lease import touch_unit_lease

_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
_LOOP_CLAIM_CLI = _LIB_DIR / "loop_claim.py"
_AUTONOMOUS_LOOP_CLI = _LIB_DIR / "autonomous_loop.py"


def _write_state(state_path: Path, **overrides) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "loop_id": "it-loop", "kind": "sub_iterate", "branch_strategy": "independent",
        "units": [],
    }
    state.update(overrides)
    state_path.write_text(json.dumps(state), encoding="utf-8")


def _run_next_batch(state_path: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_LOOP_CLAIM_CLI), "next-batch",
         "--state", str(state_path), "--campaign-worktree", str(tmp_path), "--max-parallel", "1"],
        capture_output=True, text=True,
    )


class TestConcurrentClaimsRealProcesses:
    def test_n_concurrent_claimers_never_double_claim(self, tmp_path):
        """20 units, 20 racing OS processes each asking for 1 — every unit
        must be claimed EXACTLY once, across process boundaries, relying
        entirely on ``loop.lock``'s real OS-level advisory lock (not a
        mock, not a thread-local)."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        n = 20
        _write_state(state_path, units=[
            {"id": f"U{i}", "status": "pending", "attempt": 0} for i in range(n)
        ])

        with ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(lambda _: _run_next_batch(state_path, tmp_path), range(n)))

        claimed_ids: list[str] = []
        for r in results:
            assert r.returncode in (0, 2, 4), r.stderr
            if r.returncode == 0:
                payload = json.loads(r.stdout)
                claimed_ids.extend(c["id"] for c in payload["claimed"])

        # No unit claimed twice, and every unit ends up claimed exactly once.
        assert len(claimed_ids) == n
        assert len(set(claimed_ids)) == n

        state = json.loads(state_path.read_text(encoding="utf-8"))
        statuses = {u["id"]: u["status"] for u in state["units"]}
        assert all(s == "claimed" for s in statuses.values())
        # Fencing tokens are all distinct first-claims (`attempt` stays 0,
        # no unit was raced into a re-claim/bump).
        attempt_ids = {u["attempt_id"] for u in state["units"]}
        assert len(attempt_ids) == n
        assert all(u["attempt"] == 0 for u in state["units"])


class TestLeaseReclaimAtWaveBoundary:
    def test_expired_lease_reclaimed_via_real_init_subprocess(self, tmp_path):
        """A unit `claimed` in a session that died mid-wave: its lease has
        expired by the time the NEXT `init` call (the real wave-boundary
        entry point, invoked as a real subprocess here, not called
        in-process) runs. Must reset to `pending` without bumping `attempt`
        so the next real claim mints `attempt_id`s `-a1`."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        _write_state(state_path, units=[
            {"id": "A", "status": "claimed", "attempt": 0, "attempt_id": "it-loop-A-a0"},
        ])
        # Real lease write (not hand-crafted JSON) with a `now` far enough in
        # the past that `stale_after_seconds` later has already elapsed.
        touch_unit_lease(state_path, "A", worktree="/some/worktree", branch="b",
                          attempt=0, attempt_id="it-loop-A-a0",
                          stale_after_seconds=1, now=time.time() - 1000)

        r = subprocess.run(
            [sys.executable, str(_AUTONOMOUS_LOOP_CLI), "init",
             "--state", str(state_path), "--units-from", "-", "--kind", "sub_iterate"],
            input="[]", capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["action"] == "reconciled"

        state = json.loads(state_path.read_text(encoding="utf-8"))
        unit = state["units"][0]
        assert unit["status"] == "pending"
        assert unit["attempt"] == 0  # reclaim itself never bumps
        assert unit["attempt_id"] == "it-loop-A-a0"  # survives as the "already used" sentinel

        # The unit's NEXT real claim (real subprocess again) mints `-a1`.
        r2 = _run_next_batch(state_path, tmp_path)
        assert r2.returncode == 0, r2.stderr
        claimed = json.loads(r2.stdout)["claimed"]
        assert claimed[0]["attempt"] == 1
        assert claimed[0]["attempt_id"] == "it-loop-A-a1"


class TestDependencyAncestryAssertRealGit:
    def test_unmergeable_dependency_leaves_unit_pending_batch_not_blocked(self, git_origin_repo):
        """B depends on A, but A's `merged_commit` is only reachable from a
        SIBLING branch that was never merged into local `main` — a real,
        permanent "not actually merged" case a fetch cannot fix. The
        real-git ancestry assert must leave B `pending` (never crash the
        batch, never claim it wrongly) while an unrelated, dependency-free
        unit C in the SAME batch still gets claimed."""
        work, _ = git_origin_repo
        # A commit that exists in the repo's object store but is only an
        # ancestor of `feature`, never of `main`.
        subprocess.run(["git", "-C", str(work), "checkout", "-b", "feature"],
                        capture_output=True, text=True, check=True)
        (work / "feature-file.txt").write_text("feature work", encoding="utf-8")
        subprocess.run(["git", "-C", str(work), "add", "feature-file.txt"],
                        capture_output=True, text=True, check=True)
        subprocess.run(["git", "-C", str(work), "commit", "-m", "feature work"],
                        capture_output=True, text=True, check=True)
        unmerged_sha = subprocess.run(
            ["git", "-C", str(work), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        subprocess.run(["git", "-C", str(work), "checkout", "main"],
                        capture_output=True, text=True, check=True)

        state_path = work / ".shipwright" / "loop_state.json"
        _write_state(state_path, units=[
            {"id": "A", "status": "merged", "attempt": 0, "merged_commit": unmerged_sha},
            {"id": "B", "status": "pending", "attempt": 0, "depends_on": ["A"]},
            {"id": "C", "status": "pending", "attempt": 0},
        ])

        r = subprocess.run(
            [sys.executable, str(_LOOP_CLAIM_CLI), "next-batch",
             "--state", str(state_path), "--campaign-worktree", str(work), "--max-parallel", "2"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        claimed_ids = [c["id"] for c in payload["claimed"]]
        assert claimed_ids == ["C"]  # B correctly skipped, C unaffected

        state = json.loads(state_path.read_text(encoding="utf-8"))
        by_id = {u["id"]: u["status"] for u in state["units"]}
        assert by_id["B"] == "pending"  # never claimed
        assert by_id["C"] == "claimed"

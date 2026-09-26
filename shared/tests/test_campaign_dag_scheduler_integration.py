"""Capstone integration test (campaign-dag-scheduler R6): proves R1-R5b
(depends_on schema, per-unit worktrees, review-diff attribution, state
machine + fencing, wave concurrency, serial merge lane / STRICT-STOP)
compose end to end against real git and real production entry points, in
one continuous scenario.

Five units: U1/U2/U4/U5 independent, U3 depends_on [U1, U2]. `gh pr merge`
has no Python wrapper (bash-level prose in campaign-mode.md), so it is
simulated with what it does: a real git merge of the unit's branch into the
bare origin's default branch, feeding the genuine SHA to the real
`lib.loop_mark.cmd_mark_merged`. Every state-machine transition is an
in-process call to the real cmd_* function (mirroring
test_wave_launch_failure_and_reconcile.py's style); only worktree/commit/
merge steps are real subprocess/filesystem operations.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

from lib import campaign_session_lock as csl
from lib.autonomous_loop import cmd_finalize, cmd_record
from lib.campaign_drain import run_drain
from lib.loop_claim import cmd_next_batch
from lib.loop_mark import cmd_mark, cmd_mark_merged, cmd_mark_running
from lib.loop_state import describe_blocker, is_unit_ready

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REVIEW_CLI = _REPO_ROOT / "shared" / "scripts" / "checks" / "check_review_attribution.py"
_spec = importlib.util.spec_from_file_location("check_review_attribution_for_r6_it", _REVIEW_CLI)
assert _spec is not None and _spec.loader is not None
check_review_attribution = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_review_attribution)

LOOP_ID = "r6-capstone"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)


def _diff_sha256(cwd: Path, base: str, head: str) -> str:
    """Same raw-bytes hash `review_attribution.py::pin` computes, for direct
    comparison against a pin payload's `diff_sha256`."""
    raw = subprocess.run(["git", "-C", str(cwd), "diff", f"{base}...{head}"],
                          capture_output=True, check=True).stdout
    return hashlib.sha256(raw).hexdigest()


def _add_worktree(work: Path, dirname: str, branch: str) -> Path:
    wt = work / ".worktrees" / dirname
    _git(work, "worktree", "add", str(wt), "-b", branch, "main")
    return wt


def _commit_and_push(wt: Path, filename: str, branch: str) -> str:
    (wt / filename).write_text(f"{filename}\n", encoding="utf-8")
    _git(wt, "add", filename)
    _git(wt, "commit", "-m", f"feat: {filename}")
    _git(wt, "push", "origin", branch)
    return _git(wt, "rev-parse", "HEAD").stdout.strip()


def _merge_to_origin_default(work: Path, branch: str) -> str:
    """Plays `gh pr merge --squash`'s effect via `--no-ff` (a 2-parent commit
    a real squash never produces). Harmless today -- `cmd_next_batch` checks
    the recorded `merged_commit` itself, not branch-tip ancestry, so it is
    parent-count-insensitive -- but a future parent-shape-sensitive check
    would need a real squash, not this simulation."""
    _git(work, "fetch", "origin")
    _git(work, "checkout", "main")
    _git(work, "merge", "--no-ff", f"origin/{branch}", "-m", f"merge: {branch}")
    sha = _git(work, "rev-parse", "HEAD").stdout.strip()
    _git(work, "push", "origin", "main")
    return sha


def _write_state(state_path: Path, units: list[dict]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "loop_id": LOOP_ID, "kind": "sub_iterate", "branch_strategy": "serial",
        "units": units,
    }), encoding="utf-8")


def _load_units(state_path: Path) -> list[dict]:
    """Fresh parse every call (never cached) so readiness checks rehearse a
    real resume, not in-memory reuse across waves."""
    return json.loads(state_path.read_text(encoding="utf-8"))["units"]


def _unit_row(state_path: Path, unit_id: str) -> dict:
    return next(u for u in _load_units(state_path) if u["id"] == unit_id)


def _set_fields(state_path: Path, unit_id: str, **fields) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    unit = next(u for u in state["units"] if u["id"] == unit_id)
    unit.update(fields)
    state_path.write_text(json.dumps(state), encoding="utf-8")


def _next_batch(state_path: Path, campaign_worktree: Path, max_parallel: int) -> list[dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_next_batch(argparse.Namespace(
            state=str(state_path), max_parallel=max_parallel,
            campaign_worktree=str(campaign_worktree)))
    assert rc == 0, buf.getvalue()
    return json.loads(buf.getvalue())["claimed"]


def _run_unit_to_built(state_path: Path, unit_id: str, attempt_id: str, commit: str) -> None:
    rc = cmd_mark_running(argparse.Namespace(state=str(state_path), unit=unit_id, attempt_id=attempt_id))
    assert rc == 0
    result = json.dumps({"status": "complete", "commit": commit, "tests_passed": 1, "tests_total": 1})
    rc = cmd_record(argparse.Namespace(state=str(state_path), unit=unit_id, result=result, attempt_id=attempt_id))
    assert rc == 0
    assert _unit_row(state_path, unit_id)["status"] == "built"


def _merge_and_mark_merged(state_path: Path, work: Path, unit_id: str, branch: str, attempt_id: str) -> str:
    sha = _merge_to_origin_default(work, branch)
    rc = cmd_mark(argparse.Namespace(
        state=str(state_path), unit=unit_id, status="merging", reason="capstone-it: merging",
        operator="r6-it", reason_code=None, merged_commit=None, force=False,
        confirm_no_task_running=False, campaign_worktree=None))
    assert rc == 0
    rc = cmd_mark_merged(argparse.Namespace(state=str(state_path), unit=unit_id, attempt_id=attempt_id,
                                             merged_commit=sha))
    assert rc == 0
    return sha


class TestCampaignDagSchedulerCapstoneIntegration:
    def test_full_five_unit_dag_wave_dependency_review_and_drain(self, git_origin_repo, capsys):
        work, _origin = git_origin_repo
        state_path = work / ".shipwright" / "loop_state.json"
        _write_state(state_path, [
            {"id": "U1", "status": "pending", "attempt": 0},
            {"id": "U2", "status": "pending", "attempt": 0},
            {"id": "U3", "status": "pending", "attempt": 0, "depends_on": ["U1", "U2"]},
            {"id": "U4", "status": "pending", "attempt": 0},
            {"id": "U5", "status": "pending", "attempt": 0},
        ])

        # --- Wave 1: U1/U2/U4/U5 all claim together; U3's deps are unmet. --
        wave1 = _next_batch(state_path, work, max_parallel=4)
        assert {u["id"] for u in wave1} == {"U1", "U2", "U4", "U5"}
        assert _unit_row(state_path, "U3")["status"] == "pending"
        attempts = {u["id"]: u["attempt_id"] for u in wave1}

        # --- Assertion 1: real per-unit worktrees for U1/U2 coexist, both
        # reach `built` before either merges. ------
        wt_u1 = _add_worktree(work, "U1", f"iterate/{LOOP_ID}--U1")
        wt_u2 = _add_worktree(work, "U2", f"iterate/{LOOP_ID}--U2")
        assert wt_u1.exists() and wt_u2.exists()

        commit_u1 = _commit_and_push(wt_u1, "u1.txt", f"iterate/{LOOP_ID}--U1")
        commit_u2 = _commit_and_push(wt_u2, "u2.txt", f"iterate/{LOOP_ID}--U2")
        # Both still present after both commits: proves worktree isolation
        # under sequential composition, not contention-safety -- one
        # process/thread, so it can't catch a race between truly concurrent
        # runners contending for `loop.lock` or the shared worktree.
        assert wt_u1.exists() and wt_u2.exists()

        _set_fields(state_path, "U1", worktree=str(wt_u1), branch=f"iterate/{LOOP_ID}--U1")
        _set_fields(state_path, "U2", worktree=str(wt_u2), branch=f"iterate/{LOOP_ID}--U2")
        _run_unit_to_built(state_path, "U1", attempts["U1"], commit_u1)
        _run_unit_to_built(state_path, "U2", attempts["U2"], commit_u2)

        # --- Assertion 4: review-diff attribution never cross-attributes,
        # even with a corrupted diff in the SHARED worktree (historical R3
        # bug), run at the real review point (3f-bis). --
        (work / "contamination.txt").write_text("not part of any unit's own diff\n", encoding="utf-8")
        _git(work, "add", "contamination.txt")
        _git(work, "commit", "-m", "contaminate the shared campaign worktree")
        assert (work / "contamination.txt").exists()
        assert not (wt_u1 / "contamination.txt").exists()  # never leaked into U1's own worktree

        def _pin(unit_id: str, wt: Path) -> dict:
            capsys.readouterr()  # discard prior cmd_* prints before capturing pin's own
            rc = check_review_attribution.main([
                "--mode", "pin", "--state", str(state_path), "--unit-id", unit_id,
                "--project-root", str(work), "--campaign-worktree", str(work),
                "--loop-id", LOOP_ID, "--json",
            ])
            assert rc == 0
            payload = json.loads(capsys.readouterr().out)
            # payload["worktree"] is this unit's own worktree, never the
            # shared, contaminated `work` (row's own field wins).
            assert payload["worktree"] == str(wt)
            # diff_sha256 is cross-checked against a same-method recomputation
            # of this unit's own diff -- proves internal field consistency,
            # not an independent hash implementation: it reuses the identical
            # git-diff + raw-bytes-sha256 steps pin() itself takes, so a
            # shared bug in that mechanism would pass on both sides.
            assert payload["diff_sha256"] == _diff_sha256(wt, payload["base_sha"], payload["reviewed_head"])
            return payload

        payload_u1 = _pin("U1", wt_u1)
        payload_u2 = _pin("U2", wt_u2)

        # Non-cross-attribution: neither diff sees contamination.txt; the two units' diffs/hashes differ.
        own_diff_u1 = _git(wt_u1, "diff", f"{payload_u1['base_sha']}...{payload_u1['reviewed_head']}").stdout
        own_diff_u2 = _git(wt_u2, "diff", f"{payload_u2['base_sha']}...{payload_u2['reviewed_head']}").stdout
        assert own_diff_u1.strip() != "" and own_diff_u2.strip() != ""
        assert "contamination" not in own_diff_u1
        assert "contamination" not in own_diff_u2
        assert own_diff_u1 != own_diff_u2
        assert payload_u1["diff_sha256"] != payload_u2["diff_sha256"]

        shared_head = _git(work, "rev-parse", "HEAD").stdout.strip()
        shared_base = _git(work, "merge-base", "origin/main", "HEAD").stdout.strip()
        contaminated_diff = _git(work, "diff", f"{shared_base}...{shared_head}").stdout
        assert "contamination.txt" in contaminated_diff
        assert contaminated_diff not in (own_diff_u1, own_diff_u2)

        # --- Assertions 2+3: U3 waits for BOTH deps' verified ancestry; readiness survives a fresh reload.
        u3 = _unit_row(state_path, "U3")
        assert is_unit_ready(u3, _load_units(state_path)) is False
        assert "not yet merged" in describe_blocker(u3, _load_units(state_path))

        _merge_and_mark_merged(state_path, work, "U1", f"iterate/{LOOP_ID}--U1", attempts["U1"])
        # Fresh reload (new dict, not the one above) -- still blocked on U2.
        u3 = _unit_row(state_path, "U3")
        assert is_unit_ready(u3, _load_units(state_path)) is False
        assert "U2" in describe_blocker(u3, _load_units(state_path))

        # Scheduler ENTRY POINT itself refuses U3 here (not just the helpers
        # above) -- only U1 has merged, U2 is still `built`.
        buf_mid = io.StringIO()
        with redirect_stdout(buf_mid):
            rc = cmd_next_batch(argparse.Namespace(state=str(state_path), max_parallel=5,
                                                     campaign_worktree=str(work)))
        assert rc == 4, buf_mid.getvalue()
        mid_wave = json.loads(buf_mid.getvalue())
        assert mid_wave["claimed"] == []
        assert _unit_row(state_path, "U3")["status"] == "pending"

        _merge_and_mark_merged(state_path, work, "U2", f"iterate/{LOOP_ID}--U2", attempts["U2"])
        # Another fresh reload -- now ready, deps' ancestry both verified.
        u3 = _unit_row(state_path, "U3")
        assert is_unit_ready(u3, _load_units(state_path)) is True
        assert describe_blocker(u3, _load_units(state_path)) == ""

        # Wave 2: a separate `cmd_next_batch` call re-verifies ancestry against a freshly fetched origin/main;
        # max_parallel=5 (not 1) so a duplicate claim would actually be observable.
        wave2 = _next_batch(state_path, work, max_parallel=5)
        assert [u["id"] for u in wave2] == ["U3"]

        # "Does not duplicate": one more call claims NOTHING. rc == 4 ("stalled") not 2 ("all processed") -- U3/U4/U5 are `claimed`, not TERMINAL.
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_next_batch(argparse.Namespace(state=str(state_path), max_parallel=5,
                                                     campaign_worktree=str(work)))
        assert rc == 4, buf.getvalue()
        stalled = json.loads(buf.getvalue())
        assert stalled["claimed"] == [] and stalled["blocked_pending_ids"] == []

        # --- Assertion 5: STRICT-STOP mid-wave. All 3 units are `claimed`, so only the one-shot
        # `swept_never_started` path is proven here (other drain_once branches live elsewhere) --
        # plus that the campaign session lock genuinely releases.
        session_a = "r6-it-session-A"
        csl.acquire(work, session_id=session_a)
        for uid in ("U3", "U4", "U5"):
            assert _unit_row(state_path, uid)["status"] == "claimed"

        result = run_drain(state_path, max_drain_seconds=0)
        assert result["drained"] is True
        assert {s["id"] for s in result["swept"]} == {"U3", "U4", "U5"}
        for uid in ("U3", "U4", "U5"):
            row = _unit_row(state_path, uid)
            assert row["status"] == "held"
            assert row["reason_code"] == "swept_never_started"
        # U1/U2 (already terminal, `merged`) are untouched by the drain.
        assert _unit_row(state_path, "U1")["status"] == "merged"
        assert _unit_row(state_path, "U2")["status"] == "merged"

        # R5b's policy ("release only after cmd_finalize confirms drained") is orchestrator prose, not
        # code-enforced -- cmd_finalize/csl never reference each other. Proves the two compose without
        # corrupting state, not that ordering itself is gated in code.
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_finalize(argparse.Namespace(state=str(state_path)))
        assert rc == 0, buf.getvalue()
        assert json.loads(state_path.read_text(encoding="utf-8"))["finalized"] is True

        csl.release(work, session_id=session_a)
        # A genuinely released lock lets a DIFFERENT session acquire it
        # immediately.
        csl.acquire(work, session_id="r6-it-session-B")

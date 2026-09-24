"""Wave-return reconciliation (campaign-dag-scheduler R5a): the two failure
shapes `campaign-mode.md`'s new wave loop must handle once a wave's
`Task` spawns have ALL returned, using only the state-machine primitives
R4 already built (`loop_claim.cmd_next_batch`/`cmd_release`,
`loop_mark.cmd_mark_running`, `autonomous_loop.cmd_record`) — no new
production code, only a new combined scenario across them.

- A unit still `claimed` at wave-return (the runner Task never even reached
  its own Step 1.0.5) is a LAUNCH FAILURE: released back to `pending`
  (`cmd_release`), reclaimed on the next `next-batch` call WITHOUT a double
  attempt bump.
- A unit `running` (it promoted itself past Step 1.0.5) with no
  `result.json` at wave-return (the Task errored out or exhausted its own
  turn/step budget) is demoted to `failed` via a synthetic result recorded
  through the SAME fenced `cmd_record` path a real result uses — never
  silently re-claimed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from lib.autonomous_loop import cmd_record
from lib.loop_claim import cmd_next_batch, cmd_release
from lib.loop_mark import cmd_mark_running


def _write_state(tmp_path: Path, units: list[dict]) -> Path:
    state_path = tmp_path / ".shipwright" / "loop_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"loop_id": "test-loop", "kind": "sub_iterate",
                    "branch_strategy": "independent", "units": units}),
        encoding="utf-8",
    )
    return state_path


def _unit_row(state_path: Path, unit_id: str) -> dict:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return next(u for u in state["units"] if u["id"] == unit_id)


def _batch_args(state_path: Path, *, max_parallel=1) -> argparse.Namespace:
    return argparse.Namespace(state=str(state_path), max_parallel=max_parallel,
                               campaign_worktree=None)


def _claim_first(state_path: Path) -> dict:
    """Runs `next-batch` and returns the single claimed unit's record."""
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_next_batch(_batch_args(state_path))
    assert rc == 0, buf.getvalue()
    return json.loads(buf.getvalue())["claimed"][0]


class TestLaunchFailureReleaseAndReclaim:
    def test_a_never_started_unit_is_released_then_reclaimed_without_double_bump(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "pending", "attempt": 0}])

        first = _claim_first(state_path)
        assert first["attempt"] == 0
        assert _unit_row(state_path, "A")["status"] == "claimed"

        # Launch failure: the Task never reached its own Step 1.0.5
        # mark-running — the orchestrator releases the still-`claimed` row.
        release_args = argparse.Namespace(
            state=str(state_path), unit="A", attempt_id=first["attempt_id"],
            max_attempts=3, campaign_slug=None, campaign_worktree=None,
        )
        rc = cmd_release(release_args)
        assert rc == 0
        released = _unit_row(state_path, "A")
        assert released["status"] == "pending"
        assert released["attempt"] == 0  # release itself never bumps attempt

        second = _claim_first(state_path)
        assert second["id"] == "A"
        # ONE bump for the whole release-then-reclaim cycle, not two.
        assert second["attempt"] == 1
        assert second["attempt_id"] != first["attempt_id"]

    def test_max_attempts_exhausted_marks_failed_instead_of_reclaimable(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "pending", "attempt": 0}])
        first = _claim_first(state_path)
        release_args = argparse.Namespace(
            state=str(state_path), unit="A", attempt_id=first["attempt_id"],
            max_attempts=1, campaign_slug=None, campaign_worktree=None,
        )
        rc = cmd_release(release_args)
        assert rc == 0
        assert _unit_row(state_path, "A")["status"] == "failed"

        # A `failed` unit is TERMINAL — the next wave never reclaims it.
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_next_batch(_batch_args(state_path))
        assert rc == 2  # "All units processed"


class TestRunningWithNoResultDemotedToFailed:
    def test_promoted_unit_with_no_result_is_demoted_and_never_reclaimed(self, tmp_path):
        state_path = _write_state(tmp_path, [{"id": "A", "status": "pending", "attempt": 0}])
        claimed = _claim_first(state_path)

        # The runner reached its own Step 1.0.5 promotion...
        rc = cmd_mark_running(argparse.Namespace(
            state=str(state_path), unit="A", attempt_id=claimed["attempt_id"],
        ))
        assert rc == 0
        assert _unit_row(state_path, "A")["status"] == "running"

        # ...but the Task errored out / exhausted its budget before writing
        # `result.json` at wave-return: the canonical, attempt-scoped runs
        # dir (`runs/{loop_id}/{id}/a{attempt}/`, per the spec's own
        # acceptance criteria) is empty.
        runs_dir = state_path.parent / "runs" / "test-loop" / "A" / f"a{claimed['attempt']}"
        assert not (runs_dir / "result.json").exists()

        # Orchestrator reconciliation: a synthetic failure, recorded through
        # the SAME fenced path a genuine result uses — never a silent
        # re-claim back to `pending`.
        synthetic_result = json.dumps({
            "status": "failed",
            "error": "wave-return: unit was running with no result.json "
                     "(Task errored out or exhausted its own turn/step budget)",
        })
        rc = cmd_record(argparse.Namespace(
            state=str(state_path), unit="A", result=synthetic_result,
            attempt_id=claimed["attempt_id"],
        ))
        assert rc == 3  # cmd_record's own "recorded, but not complete" exit
        demoted = _unit_row(state_path, "A")
        assert demoted["status"] == "failed"

        # A `failed` unit is TERMINAL — the next wave never reclaims it.
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_next_batch(_batch_args(state_path))
        assert rc == 2  # "All units processed" -- A stays failed, not re-offered

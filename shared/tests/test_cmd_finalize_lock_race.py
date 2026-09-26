"""Integration test for ``lib.autonomous_loop.cmd_finalize``'s round-8 fix
(campaign-dag-scheduler R5b, Tier-3 review): the "every unit is TERMINAL"
decision now happens under ``loop.lock``, closing the window where a
concurrent ``loop.lock``-respecting writer (``cmd_next_batch``,
``cmd_release``, an operator's ``loop_claim.py mark``) landing between
``run_drain()``'s last poll and this read could be silently missed by an
unlocked read, letting finalize wrongly report success on a campaign that
actually has a fresh non-terminal unit.

Uses REAL file locking (never mocked) across a background thread holding
``loop.lock``, proving ``cmd_finalize``'s own acquisition genuinely blocks
until release and then observes the state AS OF THAT MOMENT — not a stale
snapshot read before the concurrent writer's mutation landed. Placed
alongside ``test_loop_claim_concurrency_integration.py``'s real-lock style
rather than the mocked equivalents in ``test_autonomous_loop.py``.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

from lib.autonomous_loop import cmd_finalize

# Bare import, AFTER lib.autonomous_loop: that module's own `sys.path.insert`
# + bare `from file_lock import ...` already registered this module under the
# key "file_lock" -- importing it via `lib.file_lock` instead would load a
# SECOND, distinct module object (the ADR-045 lib-collision class), whose
# `LockTimeout` would not match `autonomous_loop.py`'s own `except LockTimeout`.
from file_lock import file_lock  # noqa: E402


def _write_state(state_path: Path, units: list[dict]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "loop_id": "r8-loop", "kind": "sub_iterate", "units": units,
    }), encoding="utf-8")


class TestFinalizeBlocksOnLoopLock:
    def test_finalize_observes_a_concurrent_writers_mutation_landed_while_it_waited(self, tmp_path, capsys):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        _write_state(state_path, units=[
            {"id": "A", "status": "held", "attempt": 0, "attempt_id": "a0-A",
             "reason_code": "swept_never_started"},
        ])

        lock_path = state_path.parent / "loop.lock"
        acquired = threading.Event()
        release = threading.Event()

        def hold_lock_then_mutate() -> None:
            with file_lock(lock_path, timeout_seconds=10):
                acquired.set()
                # Simulate a concurrent writer (e.g. cmd_next_batch claiming a
                # unit) landing a non-terminal transition WHILE cmd_finalize
                # is queued waiting for this same lock.
                release.wait(timeout=10)
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state["units"].append({"id": "B", "status": "claimed", "attempt": 0, "attempt_id": "a0-B"})
                state_path.write_text(json.dumps(state), encoding="utf-8")

        holder = threading.Thread(target=hold_lock_then_mutate)
        holder.start()
        assert acquired.wait(timeout=5), "background thread never acquired loop.lock"

        result: dict[str, int] = {}

        def run_finalize() -> None:
            result["rc"] = cmd_finalize(argparse.Namespace(state=str(state_path)))

        finalizer = threading.Thread(target=run_finalize)
        finalizer.start()

        # Give the finalizer thread a moment to actually reach file_lock's own
        # acquisition attempt and start blocking on it, before releasing the
        # holder -- proves the ordering rather than assuming it.
        time.sleep(0.2)
        release.set()
        holder.join(timeout=10)
        finalizer.join(timeout=10)

        assert result["rc"] == 1, (
            "cmd_finalize must refuse once it observes unit B, added while it "
            "was genuinely blocked waiting for loop.lock -- proving the read "
            "happens AFTER the concurrent writer's mutation landed, not "
            "before it (the pre-fix unlocked read would have returned 0 here, "
            "having already read the state before B was ever written)"
        )
        payload = json.loads(capsys.readouterr().err)
        assert payload["non_terminal_ids"] == ["B"]

    def test_finalize_succeeds_once_the_concurrent_writer_never_lands(self, tmp_path):
        """Control case: no concurrent mutation at all -- finalize succeeds
        exactly as before, confirming the lock adds no false refusal."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        _write_state(state_path, units=[
            {"id": "A", "status": "held", "attempt": 0, "attempt_id": "a0-A",
             "reason_code": "swept_never_started"},
        ])
        rc = cmd_finalize(argparse.Namespace(state=str(state_path)))
        assert rc == 0

    def test_finalize_persists_a_finalized_marker_before_releasing_the_lock(self, tmp_path):
        """Tier-3 review, R5b round 16, blocking: a successful strict
        finalize checked every unit was TERMINAL under `loop.lock`, then
        released the lock with no durable record that this campaign is now
        closed -- nothing stopped a concurrent `cmd_next_batch` from later
        claiming a unit that became `pending` again (an operator override,
        or a future reopen path) and leaving the campaign active despite a
        successful finalize. The success path must now persist
        `state["finalized"] = True` to `loop_state.json` itself, under the
        SAME lock the terminal-check ran under -- not merely print it in the
        summary -- so `cmd_next_batch`'s own locked reload
        (`test_loop_claim_next_batch.py::test_recheck_finalized_after_lock_
        prevents_a_claim_on_a_closed_campaign`) can observe it."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        _write_state(state_path, units=[
            {"id": "A", "status": "held", "attempt": 0, "attempt_id": "a0-A",
             "reason_code": "swept_never_started"},
        ])
        rc = cmd_finalize(argparse.Namespace(state=str(state_path)))
        assert rc == 0
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["finalized"] is True, (
            "a successful strict finalize must persist finalized=true to "
            "loop_state.json itself, not just report it in the printed "
            "summary"
        )

    def test_finalize_reports_a_structured_error_on_lock_timeout(self, tmp_path, capsys):
        """A lock genuinely held past the bound must fail closed with a
        structured JSON error, never an uncaught traceback (matching this
        function's own existing error-handling style)."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        _write_state(state_path, units=[
            {"id": "A", "status": "held", "attempt": 0, "attempt_id": "a0-A",
             "reason_code": "swept_never_started"},
        ])
        lock_path = state_path.parent / "loop.lock"
        acquired = threading.Event()
        release = threading.Event()

        def hold_lock() -> None:
            with file_lock(lock_path, timeout_seconds=10):
                acquired.set()
                release.wait(timeout=10)

        holder = threading.Thread(target=hold_lock)
        holder.start()
        assert acquired.wait(timeout=5), "background thread never acquired loop.lock"
        try:
            with patch(
                "lib.autonomous_loop.file_lock",
                lambda *a, **k: file_lock(*a, **{**k, "timeout_seconds": 0.2}),
            ):
                rc = cmd_finalize(argparse.Namespace(state=str(state_path)))
        finally:
            release.set()
            holder.join(timeout=10)

        assert rc == 1
        payload = json.loads(capsys.readouterr().err)
        assert payload["error"] == "lock_timeout"

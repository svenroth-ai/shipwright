"""Unit tests for ``lib.campaign_drain`` (campaign-dag-scheduler R5b):
STRICT-STOP sweep + bounded drain.

Mirrors the sub-iterate spec's own "dedicated STRICT-STOP test" strategy: a
stop with one unit ``pending``, one ``claimed`` (never promoted), one
``running`` — the first two go ``held`` immediately, the third finishes its
build then goes ``held``; a second scenario exercises ``max_drain_seconds``
forcing a stuck-but-heartbeating runner to ``failed``.
"""

from __future__ import annotations

import json
import time

from lib.campaign_drain import (
    DEFAULT_MAX_DRAIN_SECONDS,
    drain_once,
    remaining_active,
    run_drain,
    sweep_never_started,
)


def _unit(unit_id: str, status: str, **extra) -> dict:
    row = {"id": unit_id, "status": status, "attempt": 0, "attempt_id": f"a0-{unit_id}"}
    row.update(extra)
    return row


def _state(*units: dict) -> dict:
    return {"loop_id": "test-loop", "kind": "sub_iterate", "units": list(units)}


class TestSweepNeverStarted:
    def test_pending_and_claimed_move_to_held(self):
        state = _state(_unit("A", "pending"), _unit("B", "claimed"), _unit("C", "running"))
        swept = sweep_never_started(state)
        by_id = {u["id"]: u for u in state["units"]}
        assert {s["id"] for s in swept} == {"A", "B"}
        assert by_id["A"]["status"] == "held"
        assert by_id["A"]["reason_code"] == "swept_never_started"
        assert by_id["B"]["status"] == "held"
        assert by_id["B"]["reason_code"] == "swept_never_started"
        assert by_id["C"]["status"] == "running", "running is untouched by the sweep itself"

    def test_records_an_audit_trail_entry(self):
        state = _state(_unit("A", "pending"))
        sweep_never_started(state)
        audit = state["units"][0]["mark_audit"][-1]
        assert audit["from"] == "pending"
        assert audit["to"] == "held"
        assert audit["operator"] == "campaign-drain:strict-stop"

    def test_idempotent_second_call_sweeps_nothing(self):
        state = _state(_unit("A", "pending"))
        sweep_never_started(state)
        assert sweep_never_started(state) == []

    def test_merged_failed_held_are_never_touched(self):
        state = _state(_unit("A", "merged"), _unit("B", "failed"), _unit("C", "held"))
        assert sweep_never_started(state) == []


class TestDrainOnce:
    def test_running_unit_within_budget_is_left_alone(self):
        state = _state(_unit("A", "running", lease_expires_at=time.time() + 3600))
        actions = drain_once(state, elapsed_seconds=5, max_drain_seconds=DEFAULT_MAX_DRAIN_SECONDS)
        assert actions == []
        assert state["units"][0]["status"] == "running"

    def test_running_unit_that_finished_its_build_sweeps_to_held(self):
        """Simulates: the runner's Task, still in flight when STRICT-STOP
        fired, completes normally (F6 + record() -> "built") before the next
        drain poll."""
        state = _state(_unit("A", "built"))
        actions = drain_once(state, elapsed_seconds=5, max_drain_seconds=DEFAULT_MAX_DRAIN_SECONDS)
        assert actions == [{"id": "A", "from": "built", "to": "held", "reason_code": "swept_after_build"}]
        assert state["units"][0]["status"] == "held"

    def test_reviewed_unit_also_sweeps_to_held(self):
        state = _state(_unit("A", "reviewed"))
        actions = drain_once(state, elapsed_seconds=5, max_drain_seconds=DEFAULT_MAX_DRAIN_SECONDS)
        assert actions[0]["reason_code"] == "swept_after_build"
        assert state["units"][0]["status"] == "held"

    def test_stale_lease_running_unit_force_fails(self):
        state = _state(_unit("A", "running", lease_expires_at=time.time() - 10))
        actions = drain_once(state, elapsed_seconds=5, max_drain_seconds=DEFAULT_MAX_DRAIN_SECONDS)
        assert actions == [{"id": "A", "from": "running", "to": "failed", "reason_code": "lease_expired_during_drain"}]

    def test_running_unit_past_deadline_force_fails_even_with_live_lease(self):
        state = _state(_unit("A", "running", lease_expires_at=time.time() + 3600))
        actions = drain_once(state, elapsed_seconds=DEFAULT_MAX_DRAIN_SECONDS + 1,
                              max_drain_seconds=DEFAULT_MAX_DRAIN_SECONDS)
        assert actions == [{"id": "A", "from": "running", "to": "failed", "reason_code": "drain_timeout"}]

    def test_merging_unit_within_budget_is_left_alone(self):
        state = _state(_unit("A", "merging"))
        actions = drain_once(state, elapsed_seconds=5, max_drain_seconds=DEFAULT_MAX_DRAIN_SECONDS)
        assert actions == []
        assert state["units"][0]["status"] == "merging"

    def test_merging_unit_past_deadline_demotes_to_held_not_failed(self):
        """A stuck `gh pr checks --watch` has no lease at all (merging is
        deliberately excluded from lease-based reconcile) — only the
        deadline can force it, and it demotes to `held` (the PR may already
        be far along), never `failed`."""
        state = _state(_unit("A", "merging"))
        actions = drain_once(state, elapsed_seconds=DEFAULT_MAX_DRAIN_SECONDS + 1,
                              max_drain_seconds=DEFAULT_MAX_DRAIN_SECONDS)
        assert actions == [{"id": "A", "from": "merging", "to": "held", "reason_code": "drain_timeout"}]


class TestRemainingActive:
    def test_lists_claimed_running_merging_only(self):
        state = _state(
            _unit("A", "claimed"), _unit("B", "running"), _unit("C", "merging"),
            _unit("D", "held"), _unit("E", "merged"), _unit("F", "failed"),
        )
        assert set(remaining_active(state)) == {"A", "B", "C"}


class TestRunDrain:
    def test_full_scenario_matches_the_spec_strict_stop_test(self, tmp_path):
        """One pending, one claimed (never promoted), one running that
        finishes its build on the first poll — mirrors the sub-iterate
        spec's own STRICT-STOP test strategy word for word."""
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps(_state(
            _unit("A", "pending"), _unit("B", "claimed"), _unit("C", "running"),
        )), encoding="utf-8")

        calls = {"n": 0}

        def fake_time():
            calls["n"] += 1
            return calls["n"] * 1.0

        finished = {"done": False}

        def fake_sleep(_seconds):
            # Simulate C's runner finishing its build between polls.
            state = json.loads(state_path.read_text(encoding="utf-8"))
            for u in state["units"]:
                if u["id"] == "C":
                    u["status"] = "built"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            finished["done"] = True

        result = run_drain(state_path, max_drain_seconds=DEFAULT_MAX_DRAIN_SECONDS,
                            poll_interval_seconds=0, sleep_fn=fake_sleep, time_fn=fake_time)

        assert finished["done"]
        assert {s["id"] for s in result["swept"]} == {"A", "B"}
        final = json.loads(state_path.read_text(encoding="utf-8"))
        by_id = {u["id"]: u for u in final["units"]}
        assert by_id["A"]["status"] == "held" and by_id["A"]["reason_code"] == "swept_never_started"
        assert by_id["B"]["status"] == "held" and by_id["B"]["reason_code"] == "swept_never_started"
        assert by_id["C"]["status"] == "held" and by_id["C"]["reason_code"] == "swept_after_build"
        assert remaining_active(final) == []

    def test_max_drain_seconds_forces_a_stuck_heartbeating_runner_to_failed(self, tmp_path):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps(_state(
            _unit("C", "running", lease_expires_at=time.time() + 3600),
        )), encoding="utf-8")

        # time_fn: first call (drain start) -> 0; every poll thereafter jumps
        # straight past the deadline, so the runner is "still heartbeating"
        # (a live lease) yet never finishes.
        times = iter([0.0, 10.0])

        def fake_time():
            try:
                return next(times)
            except StopIteration:
                return 10.0

        result = run_drain(state_path, max_drain_seconds=5.0, poll_interval_seconds=0,
                            sleep_fn=lambda _s: None, time_fn=fake_time)

        final = json.loads(state_path.read_text(encoding="utf-8"))
        assert final["units"][0]["status"] == "failed"
        assert final["units"][0]["reason_code"] == "drain_timeout"
        assert result["drained"] is True

    def test_refuses_kind_section(self, tmp_path):
        state_path = tmp_path / ".shipwright" / "loop_state.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps({"loop_id": "x", "kind": "section", "units": []}),
                               encoding="utf-8")
        try:
            run_drain(state_path, sleep_fn=lambda _s: None, time_fn=time.time)
            raise AssertionError("expected ValueError for kind == 'section'")
        except ValueError as exc:
            assert "sub_iterate" in str(exc)

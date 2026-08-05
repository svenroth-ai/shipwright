"""F0 parallel-runner progress visibility and cancellable budget acquisition.

Split from ``test_suite_host_resources.py`` at ~300 lines (that file's own
docstring's three concerns: host-budget adapters, lease lifetime, and
progress visibility — the third moved here).
"""

from __future__ import annotations

import io
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as mod
import scripts.tools.suite_host_resources as host_mod
from scripts.tools.suite_budget import SuiteCancelled
from scripts.tools.run_test_suite import discover_units
from scripts.tools.suite_units import SuiteConfig


def _project(tmp_path: Path) -> Path:
    plugin = tmp_path / "plugins" / "shipwright-alpha"
    (plugin / "tests").mkdir(parents=True)
    (plugin / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    for directory in ("shared/tests", "integration-tests"):
        (tmp_path / directory).mkdir(parents=True)
    return tmp_path


def test_parallel_runner_emits_ascii_progress_heartbeat(tmp_path):
    units, stream = discover_units(_project(tmp_path))[:2], io.StringIO()

    def _slow(indexed):
        time.sleep(.04)
        return mod.UnitResult(indexed[1].id, mod.PASS, 0, .04)

    results = mod._run_parallel(units, _slow, heartbeat_seconds=.01,
                                run_id="run-München", stream=stream)
    assert [result.unit_id for result in results] == [unit.id for unit in units]
    output = stream.getvalue()
    assert "run_id=run-M\\xfcnchen" in output and "completed=0/2" in output


def test_unit_lifecycle_is_bounded_ascii_and_ordered(tmp_path, monkeypatch):
    root, stream = _project(tmp_path), io.StringIO()

    def _exec(unit, *_args, **_kwargs):
        return 0, "pass", .01, True, False, False

    monkeypatch.setattr(mod, "_exec", _exec)
    result = mod.run_suite(root, SuiteConfig(max_workers=2), budget_total=2,
                           preflight=False, run_id="run-München", stream=stream)
    assert result.exit_code == 0
    lines = [line for line in stream.getvalue().splitlines()
             if line.startswith("F0 suite unit:")]
    assert lines and all(line.isascii() and len(line) <= 1000 for line in lines)
    for unit in discover_units(root):
        own = [line for line in lines if f"unit={unit.id}" in line]
        assert "event=queued" in own[0]
        assert any("event=start" in line for line in own[1:])
        assert "event=complete" in own[-1]


def test_parallel_runner_ignores_a_closed_heartbeat_stream(tmp_path):
    class _Closed:
        def write(self, _value):
            raise BrokenPipeError("channel closed")

        def flush(self):
            raise BrokenPipeError("channel closed")

    unit = discover_units(_project(tmp_path))[0]

    def _slow(indexed):
        time.sleep(.03)
        return mod.UnitResult(indexed[1].id, mod.PASS, 0, .03)

    assert mod._run_parallel([unit], _slow, heartbeat_seconds=.01,
                             run_id="run-closed", stream=_Closed())[0].outcome == mod.PASS


def test_serial_retry_keeps_parent_heartbeat_visible(tmp_path, monkeypatch):
    root = _project(tmp_path)
    unit = discover_units(root)[0]
    stream = io.StringIO()
    monkeypatch.setattr(mod, "_run_parallel", lambda *_a, **_k: [
        mod.UnitResult(unit.id, mod.TEST_FAILURE, 1, .01, "failed")])
    monkeypatch.setattr(mod, "_clear_failed_attempt_coverage", lambda *_args: None)

    def _slow_retry(*_args, **_kwargs):
        time.sleep(.04)
        return 0, "passed", .04, True, False, False

    monkeypatch.setattr(mod, "_exec", _slow_retry)
    result = mod.run_suite(root, SuiteConfig(max_workers=1), budget_total=1,
                           preflight=False, heartbeat_seconds=.01,
                           run_id="retry-run", stream=stream)
    assert result.exit_code == 0
    output = stream.getvalue()
    assert "run_id=retry-run" in output and "phase=serial-retry" in output
    assert f"unit={unit.id}" in output
    assert "retry_kind=authoritative-serial" in output
    assert "completed=0/3" in output
    assert "initial_completed=1/3" in output
    assert "completed=3/3" not in output


def test_oversized_xdist_is_capped_for_initial_and_infra_retry(tmp_path, monkeypatch):
    root = _project(tmp_path)
    unit = discover_units(root)[0]
    calls, stream = [], io.StringIO()

    def _exec(current, _root, workers, *_args, **_kwargs):
        calls.append((current.id, workers))
        attempts = sum(item[0] == current.id for item in calls)
        return ((2, "infra", .01, False, False, False) if attempts == 1
                else (0, "pass", .01, True, False, False))

    monkeypatch.setattr(mod, "_exec", _exec)
    monkeypatch.setattr(host_mod.os, "cpu_count", lambda: 6)
    result = mod.run_suite(root, SuiteConfig(xdist={unit.id: 100}, max_workers=100),
                           budget_total=400, preflight=False, stream=stream)
    assert result.exit_code == 0
    assert [workers for unit_id, workers in calls if unit_id == unit.id] == [4, 4]
    assert "retry_kind=identical-shape-infra" in stream.getvalue()


def test_budget_never_oversubscribes_and_never_deadlocks():
    budget = mod._Budget(8)
    held = budget.acquire(8)
    done = threading.Event()

    def _waiter():
        weight = budget.acquire(4)
        done.set()
        budget.release(weight)

    thread = threading.Thread(target=_waiter, daemon=True)
    thread.start()
    assert not done.wait(.2)
    budget.release(held)
    assert done.wait(2)
    thread.join(2)
    assert mod._Budget(2).acquire(99) == 2


def test_budget_cancellation_stops_a_queued_admission():
    budget, cancel = mod._Budget(1), threading.Event()
    held = budget.acquire(1)
    outcome = []

    def _waiter():
        try:
            budget.acquire(1, cancel_event=cancel)
        except SuiteCancelled:
            outcome.append("cancelled")

    thread = threading.Thread(target=_waiter)
    thread.start()
    cancel.set()
    thread.join(2)
    budget.release(held)
    assert outcome == ["cancelled"] and not thread.is_alive()


def test_budget_checks_cancellation_before_admitting_available_capacity():
    class _SecondCheckCancels:
        calls = 0

        def is_set(self):
            self.calls += 1
            return self.calls == 1

    with pytest.raises(SuiteCancelled):
        mod._Budget(1).acquire(1, cancel_event=_SecondCheckCancels())


def test_parallel_exception_signals_cancel_and_re_raises():
    cancel = threading.Event()
    with pytest.raises(RuntimeError, match="worker failed"):
        mod._run_parallel(
            ["u"], lambda _item: (_ for _ in ()).throw(RuntimeError("worker failed")),
            heartbeat_seconds=.01, run_id="r", stream=io.StringIO(),
            cancel_event=cancel)
    assert cancel.is_set()

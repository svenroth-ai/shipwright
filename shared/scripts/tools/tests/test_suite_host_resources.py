"""F0 host-budget adapters, lease lifetime, and progress visibility."""

from __future__ import annotations

import io
import json
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as mod
import scripts.tools.suite_host_resources as host_mod
from scripts.tools.suite_budget import SuiteCancelled
from scripts.tools.run_test_suite import discover_units
from scripts.tools.suite_host_resources import hardware_cpu_budget, lease_cpu_weight
from scripts.tools.suite_units import SuiteConfig

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _project(tmp_path: Path) -> Path:
    plugin = tmp_path / "plugins" / "shipwright-alpha"
    (plugin / "tests").mkdir(parents=True)
    (plugin / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    for directory in ("shared/tests", "integration-tests"):
        (tmp_path / directory).mkdir(parents=True)
    return tmp_path


def test_every_host_request_is_capped_to_the_hardware_budget(monkeypatch):
    monkeypatch.setattr(host_mod.os, "cpu_count", lambda: 24)
    assert hardware_cpu_budget() == 22
    assert lease_cpu_weight(SuiteConfig(max_workers=440)) == 22
    assert lease_cpu_weight(SuiteConfig(max_workers=8)) == 8
    assert lease_cpu_weight(SuiteConfig()) == 22
    assert mod.cpu_budget(SuiteConfig(max_workers=440)) == 22


def test_repo_policy_allows_two_siblings_and_keeps_integration_serial():
    payload = json.loads((_REPO_ROOT / "shipwright_test_config.json").read_text(
        encoding="utf-8"))["suite"]
    assert payload["max_workers"] == 11
    assert payload["xdist"]["shared/tests"] == 8
    assert "integration-tests" not in payload["xdist"]
    unit = mod.Unit(id="integration-tests", cwd=".", target="integration-tests")
    command = mod.build_command(unit, payload["xdist"].get(unit.id))
    assert "-n" not in command and "--numprocesses" not in command


def test_f0_adapters_request_only_the_two_declared_host_resources(monkeypatch, tmp_path):
    requests = []

    @contextmanager
    def _lease(root, **kwargs):
        requests.append((root, kwargs))
        yield type("Grant", (), {"weight": kwargs["weight"]})()

    monkeypatch.setattr(host_mod, "host_resource_lease", _lease)
    monkeypatch.setattr(host_mod.os, "cpu_count", lambda: 8)
    config = SuiteConfig(max_workers=3)
    with host_mod.uv_warmup_lease(tmp_path, run_id="run-1"):
        pass
    with host_mod.f0_cpu_lease(tmp_path, config, run_id="run-1"):
        pass
    assert [(item[1]["resource"], item[1]["capacity"], item[1]["weight"])
            for item in requests] == [("uv-warmup", 1, 1), ("f0-cpu", 6, 3)]
    assert all(item[1]["run_id"] == "run-1" for item in requests)


def test_f0_host_resource_probe_uses_nonnested_uv_then_cpu(monkeypatch, tmp_path):
    events = []

    @contextmanager
    def _lease(kind, run_id):
        events.append(("enter", kind, run_id))
        yield
        events.append(("exit", kind))

    monkeypatch.setattr(host_mod, "uv_warmup_lease",
                        lambda _root, run_id: _lease("uv", run_id))
    monkeypatch.setattr(host_mod, "f0_cpu_lease",
                        lambda _root, _config, run_id: _lease("cpu", run_id))
    monkeypatch.setattr(
        sys, "argv", ["suite_host_resources.py", "--probe", "--project-root",
                      str(tmp_path), "--run-id", "probe-run"])
    assert host_mod.main() == 0
    assert events == [("enter", "uv", "probe-run"), ("exit", "uv"),
                      ("enter", "cpu", "probe-run"), ("exit", "cpu")]


def test_fingerprint_precedes_uv_and_cpu_covers_suite(monkeypatch, tmp_path):
    events = []

    @contextmanager
    def _lease(kind, weight):
        events.append(("enter", kind))
        yield SimpleNamespace(weight=weight)
        events.append(("exit", kind))

    config = SuiteConfig(xdist={"shared/tests": 2}, max_workers=3)
    monkeypatch.setattr(mod, "resolve_suite_config", lambda _root: config)
    monkeypatch.setattr(mod, "uv_warmup_lease",
                        lambda *_a, **_k: _lease("uv-warmup", 1))
    monkeypatch.setattr(mod, "f0_cpu_lease",
                        lambda *_a, **_k: _lease("f0-cpu", 3))
    monkeypatch.setattr(mod, "ensure_xdist_available",
                        lambda *_: events.append(("xdist",)))
    monkeypatch.setattr(mod, "warm_up", lambda *_: events.append(("warm",)))
    monkeypatch.setattr(mod, "source_fingerprint",
                        lambda *_: events.append(("fingerprint",)) or ("sha", None))
    monkeypatch.setattr(mod, "run_suite",
                        lambda *_a, **kw: events.append(("suite", kw)) or "result")
    with mod._run_host_leased_suite(tmp_path, "run-1") as leased:
        assert leased == ("result", "sha", None)
    assert [event[0] for event in events] == [
        "fingerprint", "enter", "xdist", "warm", "exit", "enter", "suite", "exit"]
    assert events[6][1]["budget_total"] == 3 and not events[6][1]["preflight"]


def test_source_change_during_uv_warmup_stops_final_verdict(monkeypatch, tmp_path):
    state = {"fingerprint": "before"}

    @contextmanager
    def _lease(*_args, **_kwargs):
        yield SimpleNamespace(weight=1)

    monkeypatch.setattr(mod, "resolve_suite_config", lambda _root: SuiteConfig(max_workers=1))
    monkeypatch.setattr(mod, "uv_warmup_lease", _lease)
    monkeypatch.setattr(mod, "f0_cpu_lease", _lease)
    monkeypatch.setattr(mod, "ensure_xdist_available", lambda *_args: None)
    monkeypatch.setattr(
        mod, "warm_up", lambda *_args: state.update(fingerprint="after"))
    monkeypatch.setattr(
        mod, "source_fingerprint", lambda *_args: (state["fingerprint"], None))
    monkeypatch.setattr(
        mod, "run_suite", lambda *_a, **_k: mod.SuiteResult(
            [mod.UnitResult("u", mod.PASS, 0, .01)], 0, .01))
    monkeypatch.setattr(
        mod, "emit_race_followups", lambda *_a, **_k: SimpleNamespace(failed={}))
    monkeypatch.setattr(mod, "render_run_report", lambda *_args: [])
    monkeypatch.setattr(mod, "render_retry_block", lambda *_args: [])
    assert mod._run_locked(tmp_path, "run-warm-change") == mod.GATE_FAILED


def test_cpu_lease_remains_live_until_coverage_verdict(monkeypatch, tmp_path):
    events = []

    @contextmanager
    def _leased(_root, _run_id):
        events.append("lease-enter")
        yield mod.SuiteResult([], 0, 0.1), "sha", None
        events.append("lease-exit")

    def _gate(*_args):
        assert events == ["lease-enter"]
        events.append("coverage-gate")
        return mod.GateResult(mod.GATE_PASSED, [])

    monkeypatch.setattr(mod, "_run_host_leased_suite", _leased)
    monkeypatch.setattr(mod, "emit_race_followups",
                        lambda *_a, **_k: SimpleNamespace(failed={}))
    monkeypatch.setattr(mod, "render_run_report", lambda _result: [])
    monkeypatch.setattr(mod, "render_retry_block", lambda *_args: [])
    monkeypatch.setattr(mod, "_gate_green_suite", _gate)
    assert mod._run_locked(tmp_path, "run-1") == 0
    assert events == ["lease-enter", "coverage-gate", "lease-exit"]


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

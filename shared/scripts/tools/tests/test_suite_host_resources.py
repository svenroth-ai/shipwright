"""F0 host-budget adapters and lease lifetime.

Progress-visibility / parallel-runner / budget-cancellation tests split into
``test_suite_parallel_progress.py`` at ~300 lines (mirrors this file's own
docstring's three concerns).
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.lib.iterate_timings_normalize as itn
import scripts.tools.run_test_suite as mod
import scripts.tools.suite_host_resources as host_mod
from scripts.tools.suite_host_resources import hardware_cpu_budget, lease_cpu_weight
from scripts.tools.suite_units import SuiteConfig

_REPO_ROOT = Path(__file__).resolve().parents[4]


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
        yield SimpleNamespace(weight=weight, capacity=weight, waited_seconds=0.0)
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


def test_run_suite_exception_still_records_an_incomplete_canonical_f0_active_span(
        monkeypatch, tmp_path):
    """External code review: a `run_suite()` that raises must not silently
    lose the canonical_f0_active producer boundary — exactly the run where
    attribution matters most. The exception must still propagate unchanged."""
    run_id = "iterate-2026-08-04-iterate-timing-attribution"

    @contextmanager
    def _lease(*_args, **_kwargs):
        yield SimpleNamespace(weight=1, capacity=1, waited_seconds=0.0)

    monkeypatch.setattr(mod, "resolve_suite_config", lambda _root: SuiteConfig(max_workers=1))
    monkeypatch.setattr(mod, "uv_warmup_lease", _lease)
    monkeypatch.setattr(mod, "f0_cpu_lease", _lease)
    monkeypatch.setattr(mod, "ensure_xdist_available", lambda *_args: None)
    monkeypatch.setattr(mod, "warm_up", lambda *_args: None)
    monkeypatch.setattr(mod, "source_fingerprint", lambda *_args: ("sha", None))

    def _boom(*_a, **_k):
        raise RuntimeError("suite blew up")
    monkeypatch.setattr(mod, "run_suite", _boom)

    with pytest.raises(RuntimeError, match="suite blew up"):
        with mod._run_host_leased_suite(tmp_path, run_id):
            pass

    raw = itn.read_raw_events(tmp_path, run_id)
    active_spans = [e for e in raw if e.get("name") == "canonical_f0_active"]
    assert len(active_spans) == 1
    assert active_spans[0]["outcome"] == "incomplete"


def test_source_change_during_uv_warmup_stops_final_verdict(monkeypatch, tmp_path):
    state = {"fingerprint": "before"}

    @contextmanager
    def _lease(*_args, **_kwargs):
        yield SimpleNamespace(weight=1, capacity=1, waited_seconds=0.0)

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

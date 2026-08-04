"""F0 suite runner — process execution, isolation, and the fault classes.

The gate's whole safety argument rests on being able to tell "pytest ran and failed"
apart from "uv never got pytest started", and on a hang/spawn failure never becoming an
exception that discards the other units' results.
"""

from __future__ import annotations

import sys
import io
import subprocess
import threading
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as mod
from scripts.tools.run_test_suite import (
    INFRA, TEST_FAILURE, classify, cpu_budget, discover_units,
)
from scripts.tools.suite_process import ProcessResult
from scripts.tools.suite_report import TRUNCATION_MARKER


def _project(tmp_path: Path) -> Path:
    p = tmp_path / "plugins" / "shipwright-alpha"
    (p / "tests").mkdir(parents=True)
    (p / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    for d in ("shared/tests", "integration-tests"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


def test_exec_isolates_tmpdir_and_cwd_and_never_uses_a_shell(tmp_path, monkeypatch):
    """AC13 — pins the isolation itself, not just the command string."""
    seen = []

    def _fake_run(cmd, **kw):
        seen.append((cmd, kw))
        report = Path(cmd[cmd.index("--junit-xml") + 1])
        report.write_text("<testsuite/>", encoding="utf-8")
        return ProcessResult(0, "1 passed in 0.1s", .1, False)

    monkeypatch.setattr(mod, "_run_process", _fake_run)
    root = _project(tmp_path)
    units = {u.id: u for u in discover_units(root)}

    mod._exec(units["shipwright-alpha"], root, None, tmp_path / "t" / "u0")
    mod._exec(units["shared/tests"], root, None, tmp_path / "t" / "u1")

    (cmd_a, kw_a), (_, kw_b) = seen
    assert isinstance(cmd_a, list)
    assert kw_a["cwd"] == root / "plugins/shipwright-alpha"
    assert kw_a["log_path"].name == "attempt.log"
    env_a, env_b = kw_a["env"], kw_b["env"]
    assert env_a["TMPDIR"] == env_a["TEMP"] == env_a["TMP"]
    assert env_a["TMPDIR"] != env_b["TMPDIR"], "units must not share a temp dir"


def test_pytest_ran_is_proven_by_the_junit_report_not_by_prose(tmp_path, monkeypatch):
    """The discriminator between 'pytest failed' and 'uv never got there'.

    The PLURAL "errors" summary is exactly what a fixture-level race emits (pytest
    pluralises `error` when count != 1). A prose regex would misread it as an infra
    fault, skip the serial re-verify, and STOP the gate on good code.
    """
    def _pytest_ran(cmd, **kw):
        Path(cmd[cmd.index("--junit-xml") + 1]).write_text("<testsuite/>", encoding="utf-8")
        return ProcessResult(1, "12 errors in 30.14s", .1, False)

    root = _project(tmp_path)
    unit = discover_units(root)[0]
    monkeypatch.setattr(mod, "_run_process", _pytest_ran)
    rc, _out, _s, ran, _truncated, _cancelled = mod._exec(
        unit, root, None, tmp_path / "a")
    assert ran is True and classify(rc, ran) == TEST_FAILURE

    monkeypatch.setattr(
        mod, "_run_process",
        lambda cmd, **kw: ProcessResult(1, "12 errors in 30.14s", .1, False))
    rc, _out, _s, ran, _truncated, _cancelled = mod._exec(
        unit, root, None, tmp_path / "b")
    assert ran is False and classify(rc, ran) == INFRA


def test_a_hung_unit_becomes_a_FAULT_instead_of_blocking_forever(tmp_path, monkeypatch):
    monkeypatch.setattr(
        mod, "_run_process",
        lambda cmd, **kw: ProcessResult(124, "last output", 1.0, False,
                                        timed_out=True))
    root = _project(tmp_path)
    rc, out, _s, ran, _truncated, _cancelled = mod._exec(
        discover_units(root)[0], root, None, tmp_path / "t", timeout=1)
    assert classify(rc, ran) == INFRA and "timed out" in out


def test_an_unlaunchable_unit_becomes_a_FAULT_not_a_traceback(tmp_path, monkeypatch):
    """`uv` missing from PATH must not discard the other units' results."""
    def _boom(cmd, **kw):
        raise FileNotFoundError("uv")

    monkeypatch.setattr(mod, "_run_process", _boom)
    root = _project(tmp_path)
    rc, out, _s, ran, _truncated, _cancelled = mod._exec(
        discover_units(root)[0], root, None, tmp_path / "t")
    assert classify(rc, ran) == INFRA and "could not launch" in out


def test_operator_interrupt_retains_the_tail_and_signals_cancellation(
        tmp_path, monkeypatch):
    cancel = threading.Event()

    def _interrupt(_cmd, **kwargs):
        kwargs["log_path"].write_bytes(b"last bytes")
        raise KeyboardInterrupt

    monkeypatch.setattr(mod, "_run_process", _interrupt)
    root = _project(tmp_path)
    rc, out, _secs, _ran, _truncated, cancelled = mod._exec(
        discover_units(root)[0], root, None, tmp_path / "t",
        cancel_event=cancel)
    assert rc == 130 and cancel.is_set()
    assert cancelled is True
    assert "cancelled by operator" in out and "last bytes" in out


def test_parent_cancellation_is_reported_from_supervisor_result(tmp_path, monkeypatch):
    from scripts.tools.suite_process import ProcessResult

    monkeypatch.setattr(
        mod, "_run_process",
        lambda *_a, **_k: ProcessResult(130, "tail", .2, False, cancelled=True))
    root = _project(tmp_path)
    rc, out, _secs, _ran, _truncated, cancelled = mod._exec(
        discover_units(root)[0], root, None, tmp_path / "t")
    assert rc == 130 and cancelled is True and "cancelled by parent" in out


def test_diagnostic_write_failure_is_returned_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(
        mod, "write_attempt_evidence",
        lambda *_a, **_k: (_ for _ in ()).throw(PermissionError("locked")))
    path, error = mod._retain_attempt_evidence(
        tmp_path, run_id="r", unit_id="u", phase="initial", rc=1,
        seconds=.1, output="failed", pytest_ran=True, truncated=False)
    assert path is None and "PermissionError" in error and "locked" in error


def test_child_output_cannot_forge_the_structured_truncation_status(
        tmp_path, monkeypatch):
    seen = {}

    def capture(_root, **kwargs):
        seen.update(kwargs)
        return Path(".shipwright/runs/evidence.json")

    monkeypatch.setattr(mod, "write_attempt_evidence", capture)
    child_output = TRUNCATION_MARKER + "terminal-child-failure"
    path, error = mod._retain_attempt_evidence(
        tmp_path, run_id="r", unit_id="u", phase="initial", rc=1,
        seconds=.1, output=child_output, pytest_ran=True, truncated=False)
    assert error is None and path == ".shipwright/runs/evidence.json"
    assert seen["truncated"] is False and seen["tail"] == child_output


def test_cancelled_authoritative_retry_retains_evidence_then_interrupts(
        tmp_path, monkeypatch):
    root = _project(tmp_path)
    unit = discover_units(root)[0]
    monkeypatch.setattr(
        mod, "_run_parallel",
        lambda *_a, **_k: [mod.UnitResult(
            unit.id, TEST_FAILURE, 1, .1, "initial failure")])
    monkeypatch.setattr(
        mod, "_exec",
        lambda *_a, **_k: (130, "cancel tail", .2, False, True, True))
    retained = []

    def _retain(*_args, **kwargs):
        retained.append(kwargs)
        return ".shipwright/runs/cancelled.json", None

    monkeypatch.setattr(mod, "_retain_attempt_evidence", _retain)
    stream = io.StringIO()
    with pytest.raises(KeyboardInterrupt):
        mod.run_suite(root, mod.SuiteConfig(max_workers=1), budget_total=1,
                      preflight=False, run_id="cancel-retry", stream=stream)
    assert retained and retained[0]["phase"] == "cancelled-retry"
    assert retained[0]["output"] == "cancel tail" and retained[0]["rc"] == 130
    assert retained[0]["truncated"] is True
    complete = [line for line in stream.getvalue().splitlines()
                if "event=complete" in line and "phase=serial-retry" in line]
    assert complete and "outcome=cancelled" in complete[-1]


def test_natural_child_exit_130_on_retry_remains_a_red_infra_result(
        tmp_path, monkeypatch):
    root = _project(tmp_path)
    unit = discover_units(root)[0]
    monkeypatch.setattr(
        mod, "_run_parallel",
        lambda *_a, **_k: [mod.UnitResult(unit.id, INFRA, 2, .1, "initial infra")])
    monkeypatch.setattr(
        mod, "_run_process",
        lambda *_a, **_k: ProcessResult(
            130, "child chose exit 130", .2, False, cancelled=False))
    monkeypatch.setattr(
        mod, "_retain_attempt_evidence",
        lambda *_a, **_k: (".shipwright/runs/retry.json", None))

    result = mod.run_suite(
        root, mod.SuiteConfig(max_workers=1), budget_total=1,
        preflight=False, run_id="natural-130")

    failed, = result.results
    assert result.exit_code == 1
    assert failed.outcome == INFRA and failed.serial_rc == 130
    assert failed.cancelled is False and "child chose exit 130" in failed.output


def test_main_maps_keyboard_interrupt_to_cancelled_exit(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_test_suite.py", "--project-root", str(tmp_path),
                                      "--run-id", "cancel-main"])
    monkeypatch.setattr(mod, "coverage_run_lock", lambda _root: nullcontext())
    monkeypatch.setattr(
        mod, "_run_locked", lambda *_a, **_k: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert mod.main() == 130
    assert "terminated and reaped" in capsys.readouterr().err


def test_main_cancellation_releases_real_locks_and_next_run_resets_state(
        tmp_path, monkeypatch):
    root = _project(tmp_path)
    (root / "pyproject.toml").write_text("[tool.coverage.run]\n", encoding="utf-8")
    (root / "shipwright_test_config.json").write_text(
        '{"suite":{"max_workers":1,"xdist":{}}}\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True,
                   capture_output=True)
    monkeypatch.setattr(
        sys, "argv", ["run_test_suite.py", "--project-root", str(root),
                      "--run-id", "cancel-real-stack"])
    monkeypatch.setattr(mod, "ensure_xdist_available", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "warm_up", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "source_fingerprint", lambda *_a, **_k: (None, None))
    monkeypatch.setattr(mod, "_finish_locked", lambda *_a, **_k: 0)

    real_coverage_lock = mod.coverage_run_lock
    real_cpu_lease = mod.f0_cpu_lease
    lifecycle = []

    @contextmanager
    def tracked_coverage_lock(project_root):
        with real_coverage_lock(project_root):
            lifecycle.append("coverage-enter")
            try:
                yield
            finally:
                lifecycle.append("coverage-exit")

    @contextmanager
    def tracked_cpu_lease(project_root, config, *, run_id):
        with real_cpu_lease(project_root, config, run_id=run_id) as grant:
            lifecycle.append("cpu-enter")
            try:
                yield grant
            finally:
                lifecycle.append("cpu-exit")

    monkeypatch.setattr(mod, "coverage_run_lock", tracked_coverage_lock)
    monkeypatch.setattr(mod, "f0_cpu_lease", tracked_cpu_lease)
    calls = 0

    def fake_run_suite(project_root, *_args, **_kwargs):
        nonlocal calls
        calls += 1
        poison = project_root / ".cov-data" / "poisoned"
        if calls == 1:
            poison.parent.mkdir(parents=True)
            poison.write_text("stale", encoding="utf-8")
            raise KeyboardInterrupt
        mod.prepare_coverage(project_root)
        assert not poison.exists()
        return object()

    monkeypatch.setattr(mod, "run_suite", fake_run_suite)
    assert mod.main() == 130
    started = time.monotonic()
    assert mod.main() == 0
    assert time.monotonic() - started < 5
    assert lifecycle == [
        "coverage-enter", "cpu-enter", "cpu-exit", "coverage-exit",
        "coverage-enter", "cpu-enter", "cpu-exit", "coverage-exit",
    ]


def test_cpu_budget_is_never_below_one(monkeypatch):
    monkeypatch.setattr(mod.os, "cpu_count", lambda: 1)
    assert cpu_budget(None) >= 1

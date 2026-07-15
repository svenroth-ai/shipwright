"""F0 suite runner — process execution, isolation, and the fault classes.

The gate's whole safety argument rests on being able to tell "pytest ran and failed"
apart from "uv never got pytest started", and on a hang/spawn failure never becoming an
exception that discards the other units' results.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as mod
from scripts.tools.run_test_suite import INFRA, TEST_FAILURE, classify, cpu_budget, discover_units


def _project(tmp_path: Path) -> Path:
    p = tmp_path / "plugins" / "shipwright-alpha"
    (p / "tests").mkdir(parents=True)
    (p / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    for d in ("shared/tests", "integration-tests"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


class _Proc:
    returncode, stdout, stderr = 0, "1 passed in 0.1s", ""


def test_exec_isolates_tmpdir_and_cwd_and_never_uses_a_shell(tmp_path, monkeypatch):
    """AC13 — pins the isolation itself, not just the command string."""
    seen = []

    def _fake_run(cmd, **kw):
        seen.append((cmd, kw))
        return _Proc()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    root = _project(tmp_path)
    units = {u.id: u for u in discover_units(root)}

    mod._exec(units["shipwright-alpha"], root, None, tmp_path / "t" / "u0")
    mod._exec(units["shared/tests"], root, None, tmp_path / "t" / "u1")

    (cmd_a, kw_a), (_, kw_b) = seen
    assert isinstance(cmd_a, list) and kw_a["shell"] is False
    assert kw_a["cwd"] == root / "plugins/shipwright-alpha"
    assert kw_a["capture_output"] is True and kw_a["errors"] == "replace"
    env_a, env_b = kw_a["env"], kw_b["env"]
    assert env_a["TMPDIR"] == env_a["TEMP"] == env_a["TMP"]
    assert env_a["TMPDIR"] != env_b["TMPDIR"], "units must not share a temp dir"


def test_pytest_ran_is_proven_by_the_junit_report_not_by_prose(tmp_path, monkeypatch):
    """The discriminator between 'pytest failed' and 'uv never got there'.

    The PLURAL "errors" summary is exactly what a fixture-level race emits (pytest
    pluralises `error` when count != 1). A prose regex would misread it as an infra
    fault, skip the serial re-verify, and STOP the gate on good code.
    """
    class _Failed:
        returncode, stdout, stderr = 1, "12 errors in 30.14s", ""

    def _pytest_ran(cmd, **kw):  # emulate pytest writing its --junit-xml file
        Path(cmd[cmd.index("--junit-xml") + 1]).write_text("<testsuite/>", encoding="utf-8")
        return _Failed()

    root = _project(tmp_path)
    unit = discover_units(root)[0]

    monkeypatch.setattr(mod.subprocess, "run", _pytest_ran)
    rc, _out, _s, ran = mod._exec(unit, root, None, tmp_path / "a")
    assert ran is True and classify(rc, ran) == TEST_FAILURE

    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kw: _Failed())  # no report
    rc, _out, _s, ran = mod._exec(unit, root, None, tmp_path / "b")
    assert ran is False and classify(rc, ran) == INFRA


def test_a_hung_unit_becomes_a_FAULT_instead_of_blocking_forever(tmp_path, monkeypatch):
    def _boom(cmd, **kw):
        raise mod.subprocess.TimeoutExpired(cmd, kw.get("timeout") or 1)

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    root = _project(tmp_path)
    rc, out, _s, ran = mod._exec(discover_units(root)[0], root, None, tmp_path / "t",
                                 timeout=1)
    assert classify(rc, ran) == INFRA and "timed out" in out


def test_an_unlaunchable_unit_becomes_a_FAULT_not_a_traceback(tmp_path, monkeypatch):
    """`uv` missing from PATH must not discard the other units' results."""
    def _boom(cmd, **kw):
        raise FileNotFoundError("uv")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    root = _project(tmp_path)
    rc, out, _s, ran = mod._exec(discover_units(root)[0], root, None, tmp_path / "t")
    assert classify(rc, ran) == INFRA and "could not launch" in out


def test_cpu_budget_is_never_below_one(monkeypatch):
    monkeypatch.setattr(mod.os, "cpu_count", lambda: 1)
    assert cpu_budget(None) >= 1


def test_budget_never_oversubscribes_and_never_deadlocks():
    """AC11: the outer pool and the inner xdist workers share ONE budget. A unit heavier
    than the whole budget must still be admitted (clamped) — otherwise F0 would hang."""
    budget = mod._Budget(8)
    held = budget.acquire(8)
    assert held == 8

    done = threading.Event()

    def _waiter():
        w = budget.acquire(4)  # must block until the 8 is released
        done.set()
        budget.release(w)

    t = threading.Thread(target=_waiter, daemon=True)
    t.start()
    assert not done.wait(0.2), "budget admitted work beyond its total (oversubscribed)"
    budget.release(held)
    assert done.wait(2), "budget deadlocked"
    t.join(2)

    tiny = mod._Budget(2)
    assert tiny.acquire(99) == 2, "a unit heavier than the budget must be clamped, not stuck"

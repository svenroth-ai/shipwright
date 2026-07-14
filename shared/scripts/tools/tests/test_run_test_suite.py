"""F0 suite runner — command construction, exit-code classes, the safety net.

Covers AC1/AC3/AC4/AC5/AC11/AC12/AC13 (iterate-2026-07-14-f0-parallel-suite). The
load-bearing behaviours: a unit red in parallel but green when re-run serially must NOT
stop the gate (no false STOP); a DETERMINISTIC infrastructure fault reproduces on its
retry and still stops it; and an infra retry never strips xdist — that would green a
suite that never ran the fan-out its config demands. Discovery + the config boundary
live in `test_suite_units.py`; process/fault behaviour in `test_run_test_suite_faults.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as mod
from scripts.tools.run_test_suite import (
    INFRA,
    PASS,
    TEST_FAILURE,
    SuiteConfig,
    SuiteConfigError,
    build_command,
    classify,
    discover_units,
    ensure_xdist_available,
    run_suite,
)

#: `uv run` exits 1 when it cannot build the env — pytest never ran (no report).
_UV_FAULT_OUT = "error: Failed to resolve dependencies for pytest-xdist"


def _project(tmp_path: Path, plugins=("shipwright-alpha",)) -> Path:
    for name in plugins:
        p = tmp_path / "plugins" / name
        (p / "tests").mkdir(parents=True)
        (p / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    for d in ("shared/tests", "shared/scripts/tests", "shared/scripts/tools/tests",
              "integration-tests"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


def _write_cfg(root: Path, suite) -> None:
    (root / "shipwright_test_config.json").write_text(
        json.dumps({"coverage": {"min": 70}, "suite": suite}), encoding="utf-8")


# --- AC3/AC4/AC12/AC13: command construction ---
def test_shared_dirs_keep_the_marker_expression(tmp_path):
    unit = next(u for u in discover_units(_project(tmp_path)) if u.id == "shared/tests")
    cmd = build_command(unit, None)
    assert "-m" in cmd and "not slow and not cross_plugin" in cmd


def test_xdist_only_when_allowlisted_and_dep_is_provisioned(tmp_path):
    unit = next(u for u in discover_units(_project(tmp_path)) if u.id == "shared/tests")
    plain, fanned = build_command(unit, None), build_command(unit, 8)
    assert "-n" not in plain and "pytest-xdist" not in plain
    assert fanned[fanned.index("-n") + 1] == "8"
    assert "pytest-xdist" in fanned  # AC12: provisioned, not assumed


def test_command_is_argv_never_a_shell_string(tmp_path):
    cmd = build_command(discover_units(_project(tmp_path))[0], 4)
    assert isinstance(cmd, list) and all(isinstance(a, str) for a in cmd)


# --- AC11/AC12: exit-code classes, CPU budget, xdist pre-flight ---
@pytest.mark.parametrize("rc,pytest_ran,expected", [
    (0, True, PASS),
    # rc 1 is ambiguous: `uv run` returns it for a test failure AND for its own faults.
    # The JUnit report is the PROOF (sniffing prose is unsound: pytest pluralises
    # "error" -> "errors", so a fixture-level race that ERRORs every test would be
    # misread as an infra fault and skip the serial re-verify = a FALSE STOP).
    (1, True, TEST_FAILURE),
    (1, False, INFRA),
    (2, True, INFRA), (3, True, INFRA), (4, False, INFRA), (5, True, INFRA),
    (-9, False, INFRA),
    (124, False, INFRA),   # hang
    (126, False, INFRA),   # spawn failure
])
def test_exit_code_classes(rc, pytest_ran, expected):
    assert classify(rc, pytest_ran) == expected


def test_zero_discovered_units_is_a_refusal_not_a_green_suite(tmp_path):
    """A suite that runs NOTHING must never report GREEN."""
    (tmp_path / "shipwright_test_config.json").write_text(
        json.dumps({"suite": {}}), encoding="utf-8")
    with pytest.raises(SuiteConfigError, match="no test units discovered"):
        run_suite(tmp_path)


def test_unprovisionable_xdist_is_an_actionable_error(monkeypatch, tmp_path):
    """AC12: never silently continue without the fan-out the config demands."""
    import scripts.tools.suite_units as units_mod

    class _Fail:
        returncode, stderr = 1, "error: no solution found"

    monkeypatch.setattr(units_mod.subprocess, "run", lambda *a, **k: _Fail())
    with pytest.raises(SuiteConfigError, match="pytest-xdist"):
        ensure_xdist_available(SuiteConfig(xdist={"shared/tests": 8}), tmp_path)


def test_xdist_preflight_is_skipped_when_nothing_is_allowlisted(tmp_path):
    ensure_xdist_available(SuiteConfig(xdist={}), tmp_path)  # must not raise


# --- AC5: the safety net (no false STOP; a fault is never a race) ---
def _fake_exec(script):
    """script: {unit_id: [rc_parallel, rc_serial]} — pops one rc per call.

    A non-zero rc carries REAL pytest output, so it classifies as a test failure and is
    therefore race-eligible — which is exactly what the race tests below exercise.
    """
    calls = []

    def _exec(unit, project_root, xdist_workers, tmp_dir, timeout=None):
        # tmp_dir is <root>/p/u<i> (parallel) or <root>/s/u<i> (retry)
        calls.append((unit.id, xdist_workers, tmp_dir.parent.name))
        rc = script[unit.id].pop(0)
        ran = rc in (0, 1)  # pytest produced a report unless uv died before it
        return rc, f"out-rc{rc}", 0.01, ran

    return _exec, calls


def _run(tmp_path, monkeypatch, script, xdist=None):
    root = _project(tmp_path)
    _write_cfg(root, {"xdist": xdist or {}})
    fake, calls = _fake_exec(script)
    monkeypatch.setattr(mod, "_exec", fake)
    monkeypatch.setattr(mod, "ensure_xdist_available", lambda *a, **k: None)
    return run_suite(root), calls


_GREEN = ("shipwright-alpha", "shared/scripts/tests", "shared/scripts/tools/tests",
          "integration-tests")


def test_red_in_parallel_but_green_serially_is_a_RACE_not_a_stop(tmp_path, monkeypatch):
    script = {u: [0, 0] for u in _GREEN}
    script["shared/tests"] = [1, 0]  # red parallel, green serial
    result, calls = _run(tmp_path, monkeypatch, script, xdist={"shared/tests": 4})

    assert result.exit_code == 0, "a race must never produce a false STOP"
    race = next(r for r in result.results if r.unit_id == "shared/tests")
    assert race.race is True and race.outcome == PASS
    # the re-verify ran WITHOUT xdist — that is what makes it authoritative
    assert any(c[:2] == ("shared/tests", None) for c in calls)
    # ...and in a CLEAN temp root: the authoritative verdict must not inherit the
    # failed parallel attempt's leftovers.
    reverify = [c for c in calls if c[0] == "shared/tests" and c[1] is None]
    assert reverify and reverify[0][2] == "s", \
        "the authoritative serial re-verify must not reuse the dirty parallel temp root"


def test_red_in_parallel_and_red_serially_fails_the_gate(tmp_path, monkeypatch):
    script = {u: [0, 0] for u in _GREEN}
    script["shared/tests"] = [1, 1]
    result, _ = _run(tmp_path, monkeypatch, script, xdist={"shared/tests": 4})

    assert result.exit_code == 1
    bad = next(r for r in result.results if r.unit_id == "shared/tests")
    assert bad.outcome == TEST_FAILURE and bad.race is False


@pytest.mark.parametrize("fault_rc", [2, 3, 4, 5])
def test_a_reproducing_infra_fault_fails_the_gate(tmp_path, monkeypatch, fault_rc):
    """A DETERMINISTIC fault (rc 5 = nothing collected, usage error, ...) reproduces on
    the retry and must still STOP the gate — nothing is laundered."""
    script = {u: [0, 0] for u in ("shipwright-alpha", "shared/tests",
                                  "shared/scripts/tests", "shared/scripts/tools/tests")}
    script["integration-tests"] = [fault_rc, fault_rc]
    result, _ = _run(tmp_path, monkeypatch, script)

    assert result.exit_code == 1
    bad = next(r for r in result.results if r.unit_id == "integration-tests")
    assert bad.outcome == INFRA and bad.race is False


def test_a_transient_infra_fault_recovers_but_is_reported(tmp_path, monkeypatch):
    """18 concurrent `uv` processes CREATE infra faults serial runs never had (hardlink
    races in the shared cache). Refusing them a retry would just trade a race-induced
    false STOP for an infra-induced one. It recovers — loudly."""
    script = {u: [0, 0] for u in ("shipwright-alpha", "shared/tests",
                                  "shared/scripts/tests", "shared/scripts/tools/tests")}
    script["integration-tests"] = [2, 0]   # fault, then clean
    result, _ = _run(tmp_path, monkeypatch, script)

    assert result.exit_code == 0
    healed = next(r for r in result.results if r.unit_id == "integration-tests")
    assert healed.outcome == PASS and healed.race is True
    assert healed.retry_kind == mod.RETRY_INFRA


def test_an_infra_retry_never_strips_xdist(tmp_path, monkeypatch):
    """The Stage-1 hole: if `uv` cannot provide xdist it exits 1 with no pytest report.
    Retrying that WITHOUT xdist would pass and green a suite that never ran the way the
    config demands. The infra retry therefore keeps the IDENTICAL command shape."""
    root = _project(tmp_path)
    _write_cfg(root, {"xdist": {"shared/tests": 4}})
    calls = []

    def _exec(unit, project_root, xdist_workers, tmp_dir, timeout=None):
        calls.append((unit.id, xdist_workers))
        if unit.id == "shared/tests" and xdist_workers:
            return 1, _UV_FAULT_OUT, 0.01, False   # uv died before pytest -> no report
        return 0, "ok", 0.01, True                 # an xdist-STRIPPED run would pass

    monkeypatch.setattr(mod, "_exec", _exec)
    monkeypatch.setattr(mod, "ensure_xdist_available", lambda *a, **k: None)
    result = run_suite(root)

    bad = next(r for r in result.results if r.unit_id == "shared/tests")
    assert result.exit_code == 1 and bad.outcome == INFRA and bad.race is False
    assert not any(c[:2] == ("shared/tests", None) for c in calls), \
        "the infra retry must NOT strip xdist - that would silently green a suite that " \
        "never ran the fan-out its config demands"


def test_all_green_exits_zero(tmp_path, monkeypatch):
    script = {u: [0] for u in (*_GREEN, "shared/tests")}
    result, _ = _run(tmp_path, monkeypatch, script)
    assert result.exit_code == 0 and all(r.outcome == PASS for r in result.results)

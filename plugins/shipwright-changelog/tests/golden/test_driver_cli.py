"""Every scenario and every promise test, with ``prepare`` and ``aggregate`` run through ``release.py`` (unit P3).

The scenario and promise modules are FROZEN and name ``ReplayDriver`` as a module global; this file swaps that name for
``CliDriver`` (``driver_cli``) and runs them as they are. A scenario's trace must equal the frozen ``*.trace.json`` (or an
approved delta), and a promise test must pass untouched: the conversion keeps the behaviour (programme P7, brief P3 item 6 and 8).
"""

from __future__ import annotations

import pytest

from . import scenarios_assets, scenarios_branches, scenarios_modes, scenarios_refusals, scenarios_release, scenarios_rerun, scenarios_version
from . import test_promise_aggregate, test_promise_release
from .driver_cli import CliDriver
from .scenario_core import verify

pytestmark = pytest.mark.covers("FR-01.09/AC01")  # every scenario and promise test, through the CLI driver

SCENARIO_MODULES = (scenarios_assets, scenarios_branches, scenarios_modes, scenarios_refusals, scenarios_release,
                    scenarios_rerun, scenarios_version)
PROMISE_MODULES = (test_promise_aggregate, test_promise_release)
CASES = [(sid, layout) for module in SCENARIO_MODULES for sid, scenario in module.SCENARIOS.items() for layout in scenario.layouts]


def _swap(monkeypatch, modules) -> None:
    for module in modules:
        assert module.ReplayDriver is not CliDriver
        monkeypatch.setattr(module, "ReplayDriver", CliDriver)


@pytest.mark.parametrize(("sid", "layout"), CASES, ids=[f"{s}-{lay}" for s, lay in CASES])
def test_a_scenario_through_the_cli_driver_equals_its_frozen_trace(monkeypatch, make_project, sid, layout):
    _swap(monkeypatch, SCENARIO_MODULES)
    scenario = next(m.SCENARIOS[sid] for m in SCENARIO_MODULES if sid in m.SCENARIOS)
    verify(scenario, layout, make_project)


def _promise_params(fn) -> list[dict]:
    """The ``parametrize`` cases of a promise test as keyword sets (``[{}]`` for a plain test)."""
    marks = [m for m in getattr(fn, "pytestmark", []) if m.name == "parametrize"]
    cases: list[dict] = [{}]
    for mark in marks:
        names = [n.strip() for n in (mark.args[0].split(",") if isinstance(mark.args[0], str) else mark.args[0])]
        values = [v if isinstance(v, (tuple, list)) else (v,) for v in (getattr(v, "values", v) for v in mark.args[1])]
        cases = [{**c, **dict(zip(names, v))} for c in cases for v in values]
    return cases


PROMISES = [(m, name, i) for m in PROMISE_MODULES for name, fn in vars(m).items() if name.startswith("test_")
            for i, _ in enumerate(_promise_params(fn))]


@pytest.mark.parametrize(("module", "name", "case"), PROMISES, ids=[f"{n}-{i}" for _, n, i in PROMISES])
def test_a_locked_promise_test_passes_untouched_through_the_cli_driver(monkeypatch, make_project, module, name, case):
    _swap(monkeypatch, PROMISE_MODULES)
    fn = getattr(module, name)
    fn(make_project=make_project, **_promise_params(fn)[case])


def test_the_swap_covers_every_module_that_names_the_replay_driver():
    """A scenario or promise module that names ``ReplayDriver`` and is not in a list above would silently stay on the replay."""
    import sys
    named = {m for m in sys.modules.values() if getattr(m, "__name__", "").rsplit(".", 1)[-1].startswith(("scenarios_", "test_promise_"))
             and getattr(m, "ReplayDriver", None) is not None}
    assert named <= {*SCENARIO_MODULES, *PROMISE_MODULES}, sorted(m.__name__ for m in named - {*SCENARIO_MODULES, *PROMISE_MODULES})

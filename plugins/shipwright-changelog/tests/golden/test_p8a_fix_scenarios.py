"""Unit P8a, fix round: S14d (D85) and S18c (D84), each through both drivers on a scratch project with a bare origin.

S14d: the remote's default branch is ``develop`` and the release is cut on ``main``. On commit 0b901acf3 the trunks were the
default branch and ``develop`` only, so ``main`` was a feature branch: the head was pushed and a PR opened against ``develop``.
S18c: an Edit at the preview, then Cancel. On 0b901acf3 putting the drop back was a prose instruction; now the CLI driver runs
``release.py cancel``, and the tree must be byte-identical to the one before the release started.

The two scenarios are defined next to their siblings (``scenarios_branches._s14d``, ``scenarios_modes._s18``) but not registered
there: a registered scenario needs a frozen trace, and adding one to the golden lock is a re-pin. Instead the two drivers' traces
are compared with each other, so the CLI still keeps the replay's behaviour.
"""

from __future__ import annotations

import pytest

import golden_trace as gt

from . import oracle, scenarios_branches, scenarios_modes
from .driver_cli import CliDriver
from .driver_replay import ReplayDriver
from .scenario_core import Scenario

A = "FR-01.09/"
SCENARIOS = {
    "S14d": (scenarios_branches, Scenario("S14d", ("legacy",), scenarios_branches._s14d, scenarios_branches._check_s14d,
                                          acs=(f"{A}AC01", f"{A}AC11"))),
    "S18c": (scenarios_modes, Scenario("S18c", ("legacy",), scenarios_modes._s18(True, "cancel"),
                                       scenarios_modes._check_s18(True, "cancel"), acs=(f"{A}AC10",))),
}


def _trace(monkeypatch, make_project, sid: str, driver) -> str:
    module, scenario = SCENARIOS[sid]
    monkeypatch.setattr(module, "ReplayDriver", driver)
    run = scenario.run(make_project, "legacy")
    assert isinstance(run.driver, driver)
    oracle.ASSERTED.clear()
    scenario.check(run)
    assert set(scenario.acs) <= oracle.ASSERTED, f"{sid}: the oracle never judged {sorted(set(scenario.acs) - oracle.ASSERTED)}"
    return gt.dumps(run.trace(dict(scenario.literals)))


@pytest.mark.covers("FR-01.09/AC01", "FR-01.09/AC11")
def test_s14d_with_develop_as_the_default_a_release_on_main_is_a_trunk_release_through_both_drivers(monkeypatch, make_project):
    assert _trace(monkeypatch, make_project, "S14d", ReplayDriver) == _trace(monkeypatch, make_project, "S14d", CliDriver)


@pytest.mark.covers("FR-01.09/AC10")
def test_s18c_edit_then_cancel_puts_the_edited_drop_back_through_both_drivers(monkeypatch, make_project):
    assert _trace(monkeypatch, make_project, "S18c", ReplayDriver) == _trace(monkeypatch, make_project, "S18c", CliDriver)

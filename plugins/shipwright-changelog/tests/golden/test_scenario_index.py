"""P8c and the orphan-trace guard, the two coverage checks that outlive the inventory (pilot unit P7)."""

from __future__ import annotations

import pytest

from . import oracle, scenario_index
from .scenario_core import GOLDEN_DIR

pytestmark = pytest.mark.covers("FR-01.09")  # a check of the golden-trace harness for the changelog pilot; no AC is claimed


def test_p8c_every_ac_of_fr_01_09_is_asserted_through_the_oracle():
    declared = {ac for scenario in scenario_index.all_scenarios().values() for ac in scenario.acs}
    assert scenario_index.check_p8c(declared, oracle.JUDGES) == []
    assert len(scenario_index.spec_acs()) == 15


def test_p8c_goes_red_for_an_ac_no_scenario_declares_or_no_oracle_judges():
    declared = {ac for scenario in scenario_index.all_scenarios().values() for ac in scenario.acs} - {"FR-01.09/AC12"}
    problems = scenario_index.check_p8c(declared, oracle.JUDGES - {"FR-01.09/AC05"})
    assert any("AC12" in p for p in problems) and any("AC05" in p for p in problems)


def test_every_scenario_has_its_committed_traces_and_no_trace_is_orphaned():
    expected = {s.trace_name(layout) for s in scenario_index.all_scenarios().values() for layout in s.layouts}
    assert expected == {p.name for p in GOLDEN_DIR.glob("*.trace.json")}

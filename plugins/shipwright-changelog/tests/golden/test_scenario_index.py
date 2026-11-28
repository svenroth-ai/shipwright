"""P8c and the orphan-trace guard, the two coverage checks that outlive the inventory (pilot unit P7)."""

from __future__ import annotations

import pytest

from . import oracle, scenario_index
from .scenario_core import GOLDEN_DIR

pytestmark = pytest.mark.covers("FR-01.09")  # a check of the golden-trace harness for the changelog pilot; no AC is claimed


def test_p8c_every_ac_of_fr_01_09_is_asserted_through_the_oracle():
    declared = {ac for scenario in scenario_index.all_scenarios().values() for ac in scenario.acs}
    assert scenario_index.check_p8c(declared, oracle.JUDGES) == []
    assert len(scenario_index.spec_acs()) == 16


def test_ac16_waits_for_u6_through_a_narrow_exemption_that_names_live_l1_tests():
    """U4 option B (operator, 2026-11-28): AC16 is unit-tested until U6 re-pins the prose; only AC16 is exempted, its
    tests must exist, and once a scenario or the oracle claims it the exemption must go."""
    assert set(scenario_index.UNIT_TESTED_UNTIL_U6) == {"FR-01.09/AC16"}
    assert scenario_index.check_unit_tested(scenario_index.UNIT_TESTED_UNTIL_U6) == []
    declared = {ac for scenario in scenario_index.all_scenarios().values() for ac in scenario.acs}
    assert not set(scenario_index.UNIT_TESTED_UNTIL_U6) & (declared | set(oracle.JUDGES))
    pinned = (GOLDEN_DIR / "pinned_prose" / "SKILL.md.pin").read_text(encoding="utf-8")
    assert "gh pr merge --merge --delete-branch" in pinned  # the cause: once U6 re-pins the prose, empty the map
    gone = {"FR-01.09/AC16": ("plugins/shipwright-changelog/tests/test_release_merge_ready.py::test_no_such_test",)}
    assert scenario_index.check_unit_tested(gone) == ["FR-01.09/AC16: the test " + gone["FR-01.09/AC16"][0] + " is gone"]


def test_p8c_goes_red_for_an_ac_no_scenario_declares_or_no_oracle_judges():
    declared = {ac for scenario in scenario_index.all_scenarios().values() for ac in scenario.acs} - {"FR-01.09/AC12"}
    problems = scenario_index.check_p8c(declared, oracle.JUDGES - {"FR-01.09/AC05"})
    assert any("AC12" in p for p in problems) and any("AC05" in p for p in problems)


def test_every_scenario_has_its_committed_traces_and_no_trace_is_orphaned():
    expected = {s.trace_name(layout) for s in scenario_index.all_scenarios().values() for layout in s.layouts}
    assert expected == {p.name for p in GOLDEN_DIR.glob("*.trace.json")}

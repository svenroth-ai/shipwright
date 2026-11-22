"""The coverage checks P8a-c (programme P8), green on the pinned skill prose, and proof that each one can go red."""

from __future__ import annotations


import pytest

from . import coverage, oracle
from .conftest import STEPS
from .scenario_core import GOLDEN_DIR

LINES = coverage.pinned_skill_lines()  # the pin, not the live prose: a later prose edit moves P8b only once it is approved


@pytest.mark.covers("FR-01.09/AC01")
def test_p8a_every_mechanic_ask_and_judgement_entry_names_scenarios_or_a_reason():
    assert coverage.check_p8a(coverage.all_scenarios()) == []


@pytest.mark.covers("FR-01.09/AC01")
def test_p8a_goes_red_for_an_unknown_scenario_a_missing_entry_and_a_reason_less_exemption(monkeypatch):
    table = list(coverage.EXERCISED)
    monkeypatch.setattr(coverage, "EXERCISED", [(*table[0][:3], ("S99",)), (*table[1][:3], "not_exercised: "), *table[3:]])  # entry 2 is gone
    problems = coverage.check_p8a(coverage.all_scenarios())
    assert any("S99" in p for p in problems) and any("expected exactly 1" in p for p in problems)
    assert any("needs a reason" in p for p in problems)


@pytest.mark.covers("FR-01.09/AC01")
def test_p8b_every_fenced_block_and_conditional_maps_to_a_replay_step_or_an_approved_entry():
    assert coverage.check_p8b(LINES, STEPS) == []


@pytest.mark.covers("FR-01.09/AC01")
def test_p8b_goes_red_for_a_new_block_a_new_conditional_and_a_moved_one():
    extra = [*LINES, "", "```bash", "git push --force", "```", "If the release is urgent, skip the audit."]
    problems = coverage.check_p8b(extra, STEPS)
    assert any("fenced block" in p for p in problems) and any("does not map" in p for p in problems)
    moved = ["# a new first line", *LINES]
    assert any("expects a conditional" in p for p in coverage.check_p8b(moved, STEPS))


@pytest.mark.covers("FR-01.09/AC01")
def test_p8c_every_ac_of_fr_01_09_is_asserted_through_the_oracle():
    declared = {ac for scenario in coverage.all_scenarios().values() for ac in scenario.acs}
    assert coverage.check_p8c(declared, oracle.JUDGES) == []
    assert len(coverage.spec_acs()) == 15


@pytest.mark.covers("FR-01.09/AC01")
def test_p8c_goes_red_for_an_ac_no_scenario_declares_or_no_oracle_judges():
    declared = {ac for scenario in coverage.all_scenarios().values() for ac in scenario.acs} - {"FR-01.09/AC12"}
    problems = coverage.check_p8c(declared, oracle.JUDGES - {"FR-01.09/AC05"})
    assert any("AC12" in p for p in problems) and any("AC05" in p for p in problems)


@pytest.mark.covers("FR-01.09/AC01")
def test_every_scenario_has_its_committed_traces_and_no_trace_is_orphaned():
    expected = {s.trace_name(layout) for s in coverage.all_scenarios().values() for layout in s.layouts}
    assert expected == {p.name for p in GOLDEN_DIR.glob("*.trace.json")}

"""S13, S17-S19: a dispatched run, the mode check, the preview order and the advertised ``--from``."""

from __future__ import annotations

import pytest

from .scenario_core import verify
from .scenarios_modes import SCENARIOS


@pytest.mark.covers("FR-01.09/AC01", "FR-01.09/AC11")
def test_s13_a_dispatched_run_releases_and_the_real_phase_gate_accepts_it(make_project):
    verify(SCENARIOS["S13"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01")
def test_s17a_a_token_that_does_not_resolve_stops_the_release_before_anything_runs(make_project):
    verify(SCENARIOS["S17a"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01")
def test_s17b_an_out_of_band_release_during_a_live_run_warns_and_asks(make_project):
    verify(SCENARIOS["S17b"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC10")
def test_s18a_cancel_at_the_preview_puts_nothing_back_d12(make_project):
    verify(SCENARIOS["S18a"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC10")
def test_s18b_edit_at_the_preview_keeps_the_edit_and_the_consumed_drops(make_project):
    verify(SCENARIOS["S18b"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01")
def test_s19_from_is_no_option_and_passing_it_is_refused_q7(make_project):
    verify(SCENARIOS["S19"], "legacy", make_project)

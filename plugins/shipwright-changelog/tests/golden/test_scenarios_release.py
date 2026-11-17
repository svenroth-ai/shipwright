"""S1, S1t, S2g, S2a, S2u: the whole release, driven by the replay (today's prose), asserted by the oracle.

Each test runs its scenario, checks the ACs it names through ``oracle`` and compares the normalized trace with
the committed ``*.trace.json``. A difference is a change of behaviour: regenerate on purpose (see ``scenario_core``).
"""

from __future__ import annotations

import pytest

from .scenario_core import verify
from .scenarios_release import SCENARIOS

LAYOUTS = pytest.mark.parametrize("layout", ["legacy", "drops"])


@LAYOUTS
@pytest.mark.covers("FR-01.09/AC01", "FR-01.09/AC04")
def test_s1_first_release_with_no_tag_and_an_untracked_events_file(layout, make_project):
    verify(SCENARIOS["S1"], layout, make_project)


@pytest.mark.covers("FR-01.09/AC01")
def test_s1t_a_tracked_bullet_drop_stops_the_release_before_the_tag(make_project):
    verify(SCENARIOS["S1t"], "legacy", make_project)


@LAYOUTS
@pytest.mark.covers("FR-01.09/AC02", "FR-01.09/AC04", "FR-01.09/AC06")
def test_s2g_feature_and_fix_since_1x_guided(layout, make_project):
    verify(SCENARIOS["S2g"], layout, make_project)


@LAYOUTS
@pytest.mark.covers("FR-01.09/AC02", "FR-01.09/AC04", "FR-01.09/AC06")
def test_s2a_feature_and_fix_since_1x_autonomous(layout, make_project):
    verify(SCENARIOS["S2a"], layout, make_project)


@LAYOUTS
@pytest.mark.covers("FR-01.09/AC02", "FR-01.09/AC04", "FR-01.09/AC06")
def test_s2u_feature_and_fix_since_1x_unattended(layout, make_project):
    verify(SCENARIOS["S2u"], layout, make_project)

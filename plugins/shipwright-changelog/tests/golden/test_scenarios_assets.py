"""S10-S12: decision numbers, declared manifests and the release page, asserted by the oracle and compared with the traces."""

from __future__ import annotations

import pytest

from .scenario_core import verify
from .scenarios_assets import SCENARIOS


@pytest.mark.covers("FR-01.09/AC05")
def test_s10_two_decision_drops_are_numbered_at_release_and_the_cherry_pick_fallback_is_named_back(make_project):
    verify(SCENARIOS["S10"], "drops", make_project)


@pytest.mark.covers("FR-01.09/AC12", "FR-01.09/AC13")
def test_s11a_declared_manifests_including_a_nested_catalog_carry_the_version_in_the_release_commit(make_project):
    verify(SCENARIOS["S11a"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC12")
def test_s11b_a_manifest_left_at_the_old_version_stops_the_release_before_the_tag(make_project):
    verify(SCENARIOS["S11b"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC14", "FR-01.09/AC15")
def test_s12a_the_release_page_is_created_from_the_fixture_model_and_no_old_version_gets_one(make_project):
    verify(SCENARIOS["S12a"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC14")
def test_s12b_a_condensed_text_that_fails_the_shape_check_is_never_published(make_project):
    verify(SCENARIOS["S12b"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC15")
def test_s12c_a_failed_release_page_is_reported_and_the_release_is_not_undone(make_project):
    verify(SCENARIOS["S12c"], "legacy", make_project)

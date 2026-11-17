"""S3-S9: version proposals, the empty-release stops, re-runs, legacy bullets and the dry run.

Each test runs its scenario through the replay driver, asserts the ACs it names through ``oracle`` and compares the
normalized trace with the committed ``*.trace.json`` (see ``scenario_core.verify``).
"""

from __future__ import annotations

import pytest

from .scenario_core import verify
from .scenarios_rerun import SCENARIOS as RERUN
from .scenarios_version import SCENARIOS as VERSION


@pytest.mark.covers("FR-01.09/AC04")
def test_s3_breaking_change_in_a_commit_since_0x(make_project):
    verify(VERSION["S3"], "drops", make_project)


@pytest.mark.covers("FR-01.09/AC04")
def test_s3b_breaking_change_only_in_a_drop_is_missed_today_d5(make_project):
    verify(VERSION["S3b"], "drops", make_project)


@pytest.mark.covers("FR-01.09/AC04")
def test_s4_breaking_change_since_1x(make_project):
    verify(VERSION["S4"], "drops", make_project)


@pytest.mark.covers("FR-01.09/AC03")
def test_s5a_no_commits_since_the_tag_stops(make_project):
    verify(VERSION["S5a"], "drops", make_project)


@pytest.mark.covers("FR-01.09/AC03")
def test_s5b_commits_but_no_drops_is_refused_by_fail_if_empty(make_project):
    verify(VERSION["S5b"], "drops", make_project)


@pytest.mark.covers("FR-01.09/AC07", "FR-01.09/AC06")
def test_s6_a_rerun_converges_and_the_release_date_rule(make_project):
    verify(RERUN["S6"], "drops", make_project)


@pytest.mark.covers("FR-01.09/AC07", "FR-01.09/AC08")
def test_s7a_a_rerun_with_drops_that_disagree_is_refused_and_changes_nothing(make_project):
    verify(RERUN["S7a"], "drops", make_project)


@pytest.mark.covers("FR-01.09/AC08")
def test_s7b_a_withdrawn_marking_is_not_erased(make_project):
    verify(RERUN["S7b"], "drops", make_project)


@pytest.mark.covers("FR-01.09/AC07")
def test_s7c_two_sections_claiming_the_version_stop_the_write(make_project):
    verify(RERUN["S7c"], "drops", make_project)


@pytest.mark.covers("FR-01.09/AC09")
def test_s8_legacy_bullets_are_named_back_not_folded(make_project):
    verify(RERUN["S8"], "drops", make_project)


@pytest.mark.covers("FR-01.09/AC10")
def test_s9_a_dry_run_writes_nothing(make_project):
    verify(RERUN["S9"], "drops", make_project)

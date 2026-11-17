"""S14-S15: the release from a fresh branch, from main and from a master repository; what Step 6 may commit."""

from __future__ import annotations

import pytest

from .scenario_core import verify
from .scenarios_branches import SCENARIOS


@pytest.mark.covers("FR-01.09/AC01", "FR-01.09/AC11")
def test_s14a_a_branch_the_remote_never_saw_the_request_is_refused_d7(make_project):
    verify(SCENARIOS["S14a"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01", "FR-01.09/AC11")
def test_s14b_on_main_the_event_is_committed_and_main_is_pushed_with_the_tag(make_project):
    verify(SCENARIOS["S14b"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01", "FR-01.09/AC11")
def test_s14c_on_a_master_repository_the_request_and_the_tag_push_fail_d24(make_project):
    verify(SCENARIOS["S14c"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01")
def test_s15_an_unrelated_staged_and_unstaged_file_stay_out_of_the_release_commit(make_project):
    verify(SCENARIOS["S15"], "legacy", make_project)

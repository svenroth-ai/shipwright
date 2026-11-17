"""S16a-f: the refusal paths of the release (a step that is not ok, the audit, a hook, a push, a missing gh)."""

from __future__ import annotations

import pytest

from .scenario_core import verify
from .scenarios_refusals import SCENARIOS


@pytest.mark.covers("FR-01.09/AC01")
def test_s16a_manifest_sync_that_is_not_ok_stops_before_the_commit(make_project):
    verify(SCENARIOS["S16a"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01")
def test_s16b_evidence_that_is_not_ok_stops_before_the_commit(make_project):
    verify(SCENARIOS["S16b"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01")
def test_s16c_a_release_audit_refusal_leaves_no_tag(make_project):
    verify(SCENARIOS["S16c"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01")
def test_s16d_a_pre_commit_hook_that_rejects_leaves_no_release_commit_and_no_tag(make_project):
    verify(SCENARIOS["S16d"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01", "FR-01.09/AC15")
def test_s16e_a_rejected_push_leaves_the_tag_and_the_event_on_this_machine_only(make_project):
    verify(SCENARIOS["S16e"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01", "FR-01.09/AC15")
def test_s16f_a_missing_gh_leaves_the_release_without_a_request_and_a_page(make_project):
    verify(SCENARIOS["S16f"], "legacy", make_project)

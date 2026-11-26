"""Three seeded regressions, each caught by an L2 case (programme P8, brief unit P2b).

A regression is seeded into the REPLAY (the instrument that runs today's prose), not into the shipped tools, so
the test needs no second copy of the repository: it swaps one frozen command or one step and runs the scenario
that is supposed to notice. A scenario that still passes would mean the oracle has a hole. Each case asserts the
oracle's own message, so a crash or a refusal further down the flow cannot count as "caught".
"""

from __future__ import annotations

import re
import shutil

import pytest

from . import driver_replay, scenarios_branches, scenarios_release
from .driver_replay import ReplayDriver
from .replay_commands import COMMIT_AND_TAG
from .scenario_core import trace_text

TAG = 'git tag -a v@version@ -m "Release v@version@"'


@pytest.mark.covers("FR-01.09/AC01")
def test_the_seed_helpers_change_the_chain_they_claim_to_change():
    assert TAG in COMMIT_AND_TAG and re.search(r" -- \\\n.*?@manifests@ \\\n", COMMIT_AND_TAG, re.S)


@pytest.mark.covers("FR-01.09/AC01")
def test_a_tag_on_the_parent_of_the_release_commit_is_caught(monkeypatch, make_project):
    seeded = COMMIT_AND_TAG.replace(TAG, 'git tag -a v@version@ HEAD~1 -m "Release v@version@"')
    assert seeded != COMMIT_AND_TAG
    monkeypatch.setattr(driver_replay, "COMMIT_AND_TAG", seeded)
    with pytest.raises(AssertionError, match=r"the tag v0\.1\.0 marks .*not the release commit"):
        trace_text(scenarios_release.SCENARIOS["S1"], "legacy", make_project)


@pytest.mark.covers("FR-01.09/AC01")
def test_a_release_commit_made_without_the_pathspec_is_caught(monkeypatch, make_project):
    seeded = re.sub(r" -- \\\n.*?@manifests@ \\\n", " \\\n", COMMIT_AND_TAG, flags=re.S)
    assert seeded != COMMIT_AND_TAG and "decision-drops/ .shipwright/planning/adr/ @evidence@" not in seeded
    monkeypatch.setattr(driver_replay, "COMMIT_AND_TAG", seeded)
    monkeypatch.setattr(driver_replay.ReplayDriver, "_unrelated", lambda self, scratch, paths: [])  # stop 3 (D25): else S15 stops before the commit
    with pytest.raises(AssertionError, match="swept in unrelated paths"):
        trace_text(scenarios_branches.SCENARIOS["S15"], "legacy", make_project)


class DropsKept(ReplayDriver):
    """The aggregation folds the entries but leaves the drop files behind (the regression: they were not deleted)."""

    def step_aggregate(self, scratch, version, **params):
        drops = scratch.repo / "CHANGELOG-unreleased.d"
        keep = scratch.stub_state / "kept-drops"
        if not params.get("dry_run"):
            shutil.copytree(drops, keep)
        result = super().step_aggregate(scratch, version, **params)
        if not params.get("dry_run"):
            shutil.copytree(keep, drops, dirs_exist_ok=True)
        return result


@pytest.mark.covers("FR-01.09/AC01")
def test_pending_entries_that_the_aggregation_does_not_delete_are_caught(monkeypatch, make_project):
    monkeypatch.setattr(scenarios_release, "ReplayDriver", DropsKept)
    with pytest.raises(AssertionError, match="pending entries were not consumed"):
        trace_text(scenarios_release.SCENARIOS["S1"], "legacy", make_project)

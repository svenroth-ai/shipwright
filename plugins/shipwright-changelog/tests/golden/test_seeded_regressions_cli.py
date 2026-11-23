"""The seeded regression of ``test_seeded_regressions.py`` through the CLI driver (P3 fix list item 2, unit P4).

The seeds there are swapped into the REPLAY; the shipped CLI path had none. This one seeds the same fault (the pending drops
survive the aggregation) into ``CliDriver`` and expects the oracle's own message, so the oracle cannot be blind to the CLI.
"""

from __future__ import annotations

import shutil

import pytest

from . import scenarios_release
from .driver_cli import CliDriver
from .scenario_core import trace_text


class DropsKeptCli(CliDriver):
    """The aggregation folds the entries but leaves the drop files behind."""

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
def test_pending_entries_that_the_cli_aggregation_does_not_delete_are_caught(monkeypatch, make_project):
    monkeypatch.setattr(scenarios_release, "ReplayDriver", DropsKeptCli)
    with pytest.raises(AssertionError, match="pending entries were not consumed"):
        trace_text(scenarios_release.SCENARIOS["S1"], "legacy", make_project)

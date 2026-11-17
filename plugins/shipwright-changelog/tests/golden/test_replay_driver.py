"""The replay driver itself: its citations, its step list and the stability of the traces it produces.

The scenarios (``test_scenarios_*.py``) prove today's behaviour; this file proves the instrument: every command
cites the line of ``SKILL.md`` it comes from, the driver implements exactly the steps it declares, and two runs of
a scenario in two different directories give the same trace, equal to the committed file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import golden_trace as gt

from .conftest import STEPS
from .driver_replay import ReplayDriver
from .replay_commands import CITES, NOT_REPLAYED, SKILL, fill
from .scenario_core import GOLDEN_DIR, trace_text
from .scenarios_release import SCENARIOS as RELEASE
from .scenarios_version import SCENARIOS as VERSION

pytestmark = pytest.mark.covers("FR-01.09/AC01")  # the replay instrument: every release scenario runs through it

_DRIVER_SOURCE = (GOLDEN_DIR / "driver_replay.py").read_text(encoding="utf-8")


def test_every_replay_command_cites_a_line_of_the_prose_that_holds_it():
    lines = SKILL.read_text(encoding="utf-8").splitlines()
    for key, cites in CITES.items():
        assert cites, f"{key}: no citation"
        for line, needle in cites:
            assert 0 < line <= len(lines) and needle in lines[line - 1], f"{key}: SKILL.md:{line} does not hold {needle!r}"


def test_the_commands_the_driver_runs_and_the_citation_table_name_the_same_keys():
    used = set(re.findall(r'self\._(?:run|gh|bash)\(\s*"([a-z-]+)"', _DRIVER_SOURCE))
    used |= set(re.findall(r'script, key = [^\n]*"(record-event-[a-z]+)"', _DRIVER_SOURCE))
    assert used == set(CITES), (used ^ set(CITES))


def test_what_the_replay_does_not_run_is_listed_with_a_reason():
    assert NOT_REPLAYED and all(reason.strip() for reason in NOT_REPLAYED.values())


def test_the_driver_implements_only_steps_of_the_flow_and_every_declared_step():
    driver = ReplayDriver()
    assert driver.steps <= set(STEPS)
    for step in driver.steps:
        assert callable(getattr(driver, "step_" + step.replace("-", "_")))
    assert set(STEPS) - driver.steps == {"close-phase"}  # replayed by the next unit (S13)
    with pytest.raises(KeyError):
        driver.run_step("close-phase", None)


def test_a_marker_left_unfilled_in_a_replayed_chain_is_an_error_not_a_blank():
    with pytest.raises(KeyError, match="@version@"):
        fill("git tag v@version@ @shared@", shared="/x")


def test_the_frozen_chains_match_the_prose_they_copy():
    """The chains are copies, so a drift of the prose does not change the replay; this pins that they WERE equal."""
    from .replay_commands import COMMIT_AND_TAG, EVENT_MAIN, EVENT_PR
    prose = re.sub(r"\s+", " ", SKILL.read_text(encoding="utf-8").replace("{shared_root}", "@shared@").replace("{version}", "@version@"))
    for chain in (COMMIT_AND_TAG, EVENT_PR, EVENT_MAIN):
        for command in re.findall(r"(?:^|&& )(uv run \"@shared@/scripts/tools/[a-z_]+\.py\")", chain, re.M):
            assert command in prose, command


@pytest.mark.parametrize("sid", ["S3", "S5b"])
def test_a_scenario_gives_the_same_trace_twice_and_it_is_the_committed_one(sid, make_project):
    scenario = VERSION[sid]
    (_, first), (_, second) = (trace_text(scenario, "drops", make_project) for _ in range(2))
    assert first == second
    assert (GOLDEN_DIR / scenario.trace_name("drops")).read_bytes().decode("utf-8").replace("\r\n", "\n") == first


def test_the_full_release_gives_the_same_trace_twice_and_it_is_the_committed_one(make_project):
    scenario = RELEASE["S1"]
    (_, first), (_, second) = (trace_text(scenario, "legacy", make_project) for _ in range(2))
    assert first == second
    assert (GOLDEN_DIR / scenario.trace_name("legacy")).read_bytes().decode("utf-8").replace("\r\n", "\n") == first


def test_autonomous_and_unattended_read_the_same_prose_so_their_traces_are_equal_and_differ_from_guided():
    """SKILL.md:142, :237 and :349 give 'autonomous' and 'unattended' one branch (truth table, standalone column)."""
    read = lambda name: (GOLDEN_DIR / name).read_bytes().decode("utf-8")  # noqa: E731
    for layout in ("legacy", "drops"):
        # the one difference is the word in the set-up commit ("chore: autonomy <value>"), not in the replayed steps
        assert read(f"S2a.{layout}.trace.json") == read(f"S2u.{layout}.trace.json").replace("unattended", "autonomous")
    assert read("S2a.legacy.trace.json") != read("S2g.legacy.trace.json")


def test_no_committed_trace_holds_a_path_or_a_name_of_the_machine_that_made_it():
    for trace in Path(GOLDEN_DIR).glob("*.trace.json"):
        text = trace.read_text(encoding="utf-8")
        assert not re.search(r"[A-Za-z]:[\/]|/Users/|/home/|AppData|\\Users", text), trace.name
        assert gt.SCHEMA_VERSION == 1 and '"schema": 1' in text

"""What the golden root still needs from the retired coverage checks (pilot unit P7).

The coverage checks P8a-c lived in ``coverage.py``. P7 retired it with the inventory: P8a read ``inventory.json`` and
P8b mapped the pinned prose's line numbers to replay steps, and neither survives the thin ``SKILL.md``. What does not
depend on the inventory stays here, read-only: the FR-01.09 AC ids of the adopted spec (``spec_acs``), every scenario by
id (``all_scenarios``) and **P8c**, every AC judged by an oracle function and asserted by a scenario (``check_p8c``).
The tests are in ``test_scenario_index.py``; ``test_promises_meta.py`` reads the spec and the scenarios through here.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable

from .replay_commands import REPO_ROOT

SPEC = REPO_ROOT / ".shipwright/planning/01-adopted/spec.md"
JUDGEMENT_ONLY: dict[str, str] = {}
# An AC no replay scenario can assert yet, with the L1 tests that cover it until then (``check_unit_tested`` keeps them
# real). AC16 (U4, operator decision 2026-11-28, option B): the replay driver follows the pinned stop-3 prose, which
# still merges with ``gh pr merge --merge``; U6 re-pins that prose, binds AC16 to a scenario and empties this map.
UNIT_TESTED_UNTIL_U6: dict[str, tuple[str, ...]] = {
    "FR-01.09/AC16": (
        "plugins/shipwright-changelog/tests/test_release_merge_ready.py::test_the_method_follows_the_repository_settings_and_prefers_a_merge_commit",
        "plugins/shipwright-changelog/tests/test_release_merge_ready.py::test_a_squash_onto_a_base_that_moved_stops_with_a_plain_restart_message",
        "plugins/shipwright-changelog/tests/test_release_merge_ready_e2e.py::test_a_repo_that_allows_merge_commits_gets_a_pinned_merge_line_and_the_tag_stays_on_the_release",
        "plugins/shipwright-changelog/tests/test_release_merge_ready_e2e.py::test_a_base_that_moved_stops_before_a_squash_with_a_restart_message_and_nothing_is_merged",
        "plugins/shipwright-changelog/tests/test_release_merge_ready_e2e.py::test_a_commit_pushed_to_the_branch_after_the_answer_makes_the_host_refuse_the_pinned_line",
    ),
}


def spec_acs() -> list[str]:
    """The AC ids of FR-01.09 as ``FR-01.09/ACnn``, read from the adopted spec."""
    text = SPEC.read_text(encoding="utf-8")
    block = text.split("### FR-01.09 —", 1)[1].split("\n### FR-", 1)[0]
    return [f"FR-01.09/{ac}" for ac in dict.fromkeys(re.findall(r"\[(AC\d+)\]", block))]


def check_p8c(tagged: Iterable[str], oracle_acs: Iterable[str]) -> list[str]:
    """``tagged``: the ACs the scenarios declare (``Scenario.acs``); ``oracle_acs``: the ACs an oracle function judges."""
    declared, judged = set(tagged), set(oracle_acs)
    problems = []
    for ac in spec_acs():
        if ac in JUDGEMENT_ONLY or ac in UNIT_TESTED_UNTIL_U6:
            continue
        if ac not in judged:
            problems.append(f"{ac}: no oracle function judges it")
        if ac not in declared:
            problems.append(f"{ac}: no scenario asserts it through the oracle")
    return problems


def check_unit_tested(exempt: dict[str, tuple[str, ...]]) -> list[str]:
    """Each exempted AC is still in the spec and names L1 tests that exist (``path::name``) in a file that skips nothing
    (no ``skip``/``xfail`` anywhere in it, so a skipped test cannot keep the exemption green)."""
    problems = []
    for ac, tests in exempt.items():
        if ac not in spec_acs():
            problems.append(f"{ac}: exempted but not in the spec")
        if not tests:
            problems.append(f"{ac}: exempted without a test")
        for check in tests:
            path, _, name = check.partition("::")
            file = REPO_ROOT / path
            source = file.read_text(encoding="utf-8") if file.is_file() else ""
            defs = {n.name for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
            if name not in defs:
                problems.append(f"{ac}: the test {check} is gone")
            elif re.search(r"\b(skip|skipif|xfail|importorskip)\b", source):
                problems.append(f"{ac}: the file of {check} skips or xfails a test")
    return problems


def all_scenarios() -> dict:
    """Every scenario of the golden root, by id (the modules are imported here, so this file can be read first)."""
    from . import scenarios_assets, scenarios_branches, scenarios_modes, scenarios_refusals, scenarios_release
    from . import scenarios_rerun, scenarios_version
    merged: dict = {}
    for module in (scenarios_release, scenarios_version, scenarios_rerun, scenarios_assets, scenarios_branches,
                   scenarios_refusals, scenarios_modes):
        assert not set(merged) & set(module.SCENARIOS), "a scenario id is defined twice"
        merged.update(module.SCENARIOS)
    return merged

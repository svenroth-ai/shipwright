"""What the golden root still needs from the retired coverage checks (pilot unit P7).

The coverage checks P8a-c lived in ``coverage.py``. P7 retired it with the inventory: P8a read ``inventory.json`` and
P8b mapped the pinned prose's line numbers to replay steps, and neither survives the thin ``SKILL.md``. What does not
depend on the inventory stays here, read-only: the FR-01.09 AC ids of the adopted spec (``spec_acs``), every scenario by
id (``all_scenarios``) and **P8c**, every AC judged by an oracle function and asserted by a scenario (``check_p8c``).
The tests are in ``test_scenario_index.py``; ``test_promises_meta.py`` reads the spec and the scenarios through here.
"""

from __future__ import annotations

import re
from typing import Iterable

from .replay_commands import REPO_ROOT

SPEC = REPO_ROOT / ".shipwright/planning/01-adopted/spec.md"
JUDGEMENT_ONLY: dict[str, str] = {}


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
        if ac in JUDGEMENT_ONLY:
            continue
        if ac not in judged:
            problems.append(f"{ac}: no oracle function judges it")
        if ac not in declared:
            problems.append(f"{ac}: no scenario asserts it through the oracle")
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

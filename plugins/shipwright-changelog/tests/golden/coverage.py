"""The coverage checks of the programme (P8a-c): what the scenarios exercise, in both directions.

* **P8a** every inventory entry of class ``mechanic``, ``ask`` or ``judgement`` names the scenarios that exercise it,
  or carries ``not_exercised`` with a reason the operator approves (``EXERCISED``).
* **P8b** every fenced block and every conditional of ``SKILL.md`` maps to a replay step or a ``NOT_REPLAYED`` entry
  (``CONDITIONALS`` for the conditionals; the blocks are matched by the lines ``CITES`` and ``NOT_REPLAYED`` name).
* **P8c** every AC of FR-01.09 is judged by the oracle in at least one scenario, or is listed judgement-only
  (``JUDGEMENT_ONLY``, empty: every AC has an oracle function and a scenario).

The inventory and the prose are read from the repository as they stand. At stop 2 the prose copy is pinned by hash
and P8b is pointed at the pin (programme P7); P7 of the pilot retires the inventory with its checker. This module
only reads; the tests are in ``test_coverage_checks.py``.
"""

from __future__ import annotations

import json
import re
from typing import Iterable

from .replay_commands import CITES, NOT_REPLAYED, REPO_ROOT

INVENTORY = REPO_ROOT / ".shipwright/planning/campaigns/2026-10-25-dfp-pilot-changelog-inventory/inventory.json"
SPEC = REPO_ROOT / ".shipwright/planning/01-adopted/spec.md"
NOT_EXERCISED = "not_exercised: "
JUDGEMENT_ONLY: dict[str, str] = {}

# (file, last heading of the section, start of the part's ``what`` or "") -> scenario ids, or "not_exercised: <reason>"
EXERCISED: list[tuple[str, str, str, tuple[str, ...] | str]] = [
    ("SKILL.md", "A. Print Intro Banner", "", ("S19",)),
    ("SKILL.md", "B. Discover Plugin Root", "", NOT_EXERCISED + "an environment variable the host injects (SHIPWRIGHT_PLUGIN_ROOT); the replay passes the plugin path itself"),
    ("SKILL.md", "C. Detect Invocation Mode", "resolve the mode", ("S13", "S17a", "S17b")),
    ("SKILL.md", "C. Detect Invocation Mode", "error mode", ("S17a",)),
    ("SKILL.md", "C. Detect Invocation Mode", "standalone notice", NOT_EXERCISED + "printed text, no command and no state"),
    ("SKILL.md", "C. Detect Invocation Mode", "out-of-sequence", ("S17b",)),
    ("SKILL.md", "D. Run Setup Script", "", ("S1", "S2g", "S5a")),
    ("SKILL.md", "Step 0: Phase Session Context Recovery", "", ("S13",)),
    ("SKILL.md", "Step 1: Analyze Git History", "", ("S5a", "S1")),
    ("SKILL.md", "Step 2: Categorize Commits", "", ("S1", "S3")),
    ("SKILL.md", "Step 3: Determine Version Bump", "use suggested_version", ("S3", "S4", "S2g")),
    ("SKILL.md", "Step 3: Determine Version Bump", "guided:", ("S2g",)),
    ("SKILL.md", "Step 3: Determine Version Bump", "autonomous or unattended", ("S2a", "S2u")),
    ("SKILL.md", "Step 4: Generate Changelog Entry", "upgrade-notes check: list", NOT_EXERCISED + "needs a project whose migration pages changed since the tag; no brief scenario builds one (finding D12)"),
    ("SKILL.md", "Step 4: Generate Changelog Entry", "upgrade-notes check: read", NOT_EXERCISED + "judgement: a model reads the pages (NOT_REPLAYED)"),
    ("SKILL.md", "Step 4: Generate Changelog Entry", "aggregate:", ("S2g", "S6", "S9")),
    ("SKILL.md", "Step 4: Generate Changelog Entry", "legacy bullets", ("S8", "S10")),
    ("SKILL.md", "Step 4: Generate Changelog Entry", "refused re-run", ("S7a", "S7b", "S7c")),
    ("SKILL.md", "Step 4: Generate Changelog Entry", "cherry-pick fallback", ("S10",)),
    ("SKILL.md", "ADR decision-drops", "", ("S10",)),
    ("SKILL.md", "Step 5: Preview and Confirm", "autonomous:", ("S2a", "S2u")),
    ("SKILL.md", "Step 5: Preview and Confirm", "guided:", ("S2g", "S18a", "S18b")),
    ("SKILL.md", "Step 5: Preview and Confirm", "edit:", ("S18b",)),
    ("SKILL.md", "Step 5.3: Fold Old Event Files (automatic housekeeping)", "", ("S2g",)),
    ("SKILL.md", "Step 5.4: Sync Published Package Manifests", "", ("S11a", "S11b", "S16a")),
    ("SKILL.md", "Step 5.5: Refresh the Compliance Evidence Documents", "", ("S2g", "S16b")),
    ("SKILL.md", "Step 6: Commit and Tag", "", ("S1", "S15", "S16c", "S16d", "S11b")),
    ("SKILL.md", "Step 7: Create PR (Optional)", "open the PR", ("S2g", "S14a", "S14c", "S16f")),
    ("SKILL.md", "Step 7: Create PR (Optional)", "record the changelog event", ("S1", "S14b", "S16e")),
    ("SKILL.md", "Step 7: Create PR (Optional)", "autonomous: merge", ("S2a", "S2u")),
    ("SKILL.md", "Step 7: Create PR (Optional)", "push the head", ("S14a", "S14c", "S16e")),
    ("SKILL.md", "Step 7: Create PR (Optional)", "release page", ("S12a", "S12b", "S12c")),
    ("SKILL.md", "Step 7: Create PR (Optional)", "canon C1-C3", ("S13",)),
    ("SKILL.md", "Step 7: Create PR (Optional)", "print the closing summary", NOT_EXERCISED + "printed text, no command"),
    ("references/event-fold.md", "Reading the result", "", NOT_EXERCISED + "needs old per-run event files to fold; no brief scenario builds them (the fold step itself runs in every full release)"),
    ("references/first-actions.md", "Single-Session Gate Discipline", "", ("S13",)),
    ("references/release-workflow.md", "Upgrade-notes check (first thing in Step 4, every mode)", "list migration", NOT_EXERCISED + "same as SKILL.md Step 4: no scenario with a changed migration page"),
    ("references/release-workflow.md", "Upgrade-notes check (first thing in Step 4, every mode)", "read each page", NOT_EXERCISED + "judgement: a model reads the pages"),
]

# Conditionals of SKILL.md (a line that starts one) -> (needle of the line, "step:<replay step>" or "not_replayed:<key>")
CONDITIONALS: dict[int, tuple[str, str]] = {
    50: ("Omit `--phase-task-id`", "step:prepare"),
    53: ("- **`pipeline`**", "step:prepare"),
    58: ("- **`standalone`**", "step:prepare"),
    63: ("If `requires_out_of_sequence_warning`", "step:prepare"),
    67: ("- **`error`**", "step:prepare"),
    85: ("If the orchestrator handed you", "step:prepare"),
    103: ("If no commits since last tag", "step:prepare"),
    142: ("**Autonomous mode**", "step:prepare"),
    145: ("**Guided mode**", "step:prepare"),
    237: ("**Autonomous mode**", "step:preview"),
    240: ("**Guided mode**", "step:preview"),
    251: ("If edit:", "step:preview"),
    278: ("`status: \"ok\"` → proceed", "step:sync"),
    292: ("`status: \"ok\"` → proceed", "step:evidence"),
    327: ("**Only if on a feature branch**", "step:open-pr"),
    349: ("**Autonomous / unattended mode:**", "step:merge-pr"),
    354: ("**Guided mode:**", "step:open-pr"),
    356: ("**If already on main:**", "step:record-event"),
    376: ("Read `status` from the JSON", "step:release-page"),
}
_CONDITIONAL = re.compile(r"^\s*(?:- )?(?:\*\*)?(?:If\b|Only if\b|Omit\b|Autonomous\b|Guided\b|`status: \"ok\"`|Read `status`"
                          r"|`(?:pipeline|standalone|error)`\*\*)")
_PIPELINE_ITEM = re.compile(r"^- \*\*`(?:pipeline|standalone|error)`\*\*")


def fenced_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """``(open line, close line)``, 1-based, of every fenced block."""
    blocks, start = [], None
    for number, line in enumerate(lines, 1):
        if line.startswith("```"):
            if start is None:
                start = number
            else:
                blocks.append((start, number))
                start = None
    return blocks


def conditionals(lines: list[str]) -> dict[int, str]:
    """Every conditional line outside the fenced blocks: line number -> text."""
    inside = {n for a, b in fenced_blocks(lines) for n in range(a, b + 1)}
    return {n: ln for n, ln in enumerate(lines, 1)
            if n not in inside and (_CONDITIONAL.match(ln) or _PIPELINE_ITEM.match(ln))}


def not_replayed_ranges() -> list[tuple[int, int]]:
    ranges = []
    for key in NOT_REPLAYED:
        found = re.match(r"SKILL\.md:(\d+)(?:-(\d+))?", key)
        if found:
            ranges.append((int(found.group(1)), int(found.group(2) or found.group(1))))
    return ranges


def check_p8b(lines: list[str], steps: Iterable[str]) -> list[str]:
    """Problems: a fenced block no cited line or approved ``NOT_REPLAYED`` range touches, a conditional that is not in the
    table (or whose line moved), a table entry that points at a step the replay does not have."""
    problems: list[str] = []
    cited = {line for cites in CITES.values() for line, _ in cites}
    skipped = not_replayed_ranges()
    for start, end in fenced_blocks(lines):
        if not any(start <= c <= end for c in cited) and not any(a <= start and end <= b for a, b in skipped):
            problems.append(f"SKILL.md:{start}-{end}: a fenced block no replay command cites and NOT_REPLAYED does not list")
    live = conditionals(lines)
    for number, text in live.items():
        if number not in CONDITIONALS:
            problems.append(f"SKILL.md:{number}: a conditional the table does not map: {text.strip()[:60]!r}")
    for number, (needle, target) in CONDITIONALS.items():
        if number not in live or needle not in live[number]:
            problems.append(f"SKILL.md:{number}: the table expects a conditional with {needle!r} here")
        kind, _, name = target.partition(":")
        if (kind == "step" and name not in set(steps)) or (kind == "not_replayed" and not any(name in k for k in NOT_REPLAYED)):
            problems.append(f"SKILL.md:{number}: {target!r} is not a replay step or a NOT_REPLAYED entry")
    return problems


def inventory_entries() -> list[tuple[str, str, str, str]]:
    """``(file, last heading, what, class)`` of every mechanic, ask or judgement entry, parts included."""
    entries = []
    for section in json.loads(INVENTORY.read_text(encoding="utf-8"))["sections"]:
        tail = section["path"].split(" > ")[-1]
        for item in [section, *section.get("parts", [])]:
            if item["class"] in ("mechanic", "ask", "judgement"):
                entries.append((section["file"], tail, item.get("what", ""), item["class"]))
    return entries


def check_p8a(scenario_ids: Iterable[str]) -> list[str]:
    problems: list[str] = []
    known, used = set(scenario_ids), set()
    for file, tail, what, cls in inventory_entries():
        hits = [i for i, (f, t, w, _) in enumerate(EXERCISED) if (f, t) == (file, tail) and what.startswith(w)]
        if len(hits) != 1:
            problems.append(f"{file} > {tail} [{what[:40]}] ({cls}): {len(hits)} coverage entries, expected exactly 1")
            continue
        used.add(hits[0])
        value = EXERCISED[hits[0]][3]
        if isinstance(value, str):
            if not value.startswith(NOT_EXERCISED) or not value[len(NOT_EXERCISED):].strip():
                problems.append(f"{file} > {tail}: a not_exercised entry needs a reason")
        else:
            problems += [f"{file} > {tail}: names {sid}, which is not a scenario" for sid in value if sid not in known]
    problems += [f"coverage entry {EXERCISED[i][:3]} matches no inventory entry" for i in range(len(EXERCISED)) if i not in used]
    return problems


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

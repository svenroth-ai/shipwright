"""Spec-time scope check for `/shipwright-project` (atomic-frs U1): the CODE half of "an FR names one capability".

At spec-writing time there is no code and no test, so the cluster evidence of :mod:`lib.fr_clusters` does not exist yet. What
code CAN check on a freshly written ``spec.md`` is deliberately conservative: it blocks only what the skill's own rules
(``spec-generation.md``, ``fr-authoring.md`` §4a) never allow, and never a shape the skill itself prescribes.

**Problems (block: the CLI exits 1):**

* the spec has text but no requirement this check can read;
* an FR has no acceptance criteria at all AND is ``Must`` or its priority cannot be read as ``Should`` / ``May`` (a ``Should`` or
  ``May`` requirement may legitimately have none yet);
* a criterion carries a file path or a code symbol (``fr-authoring.md`` §1/§5). Product names such as LinkedIn or WordPress are
  not code symbols.

**Prompts (printed, never change the exit code):**

* a criterion that is not ``Given ... when ... then ...`` (the skill's own checkbox examples are not in that shape, and §4a
  settlement criteria are not either);
* a criterion naming an HTTP verb, an ADR number or an iterate slug;
* a name joining two capabilities with "and" - "Terms and conditions" is one capability. It is the cue to apply the AI
  capability test (``§3c``: one plain sentence without "and", per group of criteria).

Rows under a "Removed Requirements" heading are retired and skipped. Stdlib plus the shared form checkers.
"""

from __future__ import annotations

import re

from lib.ac_catalog import parse_catalog
from lib.fr_criterion_shape import is_well_formed_criterion
from lib.fr_hygiene_detectors import violations

__all__ = ["check_spec"]

_MARKUP = re.compile(r"^-\s*(?:\[[ xX]\]\s*)?(?:\([A-Z]\)\s*)?(?:\[AC\d+\]\s*)?")
_JOINS = re.compile(r"\s(?:and|und|&|plus)\s", re.IGNORECASE)
#: Product names, measurement units and ``*.js`` framework names that look like symbols or file names but are plain vocabulary.
_BRANDS = re.compile(r"\b(?:LinkedIn|WhatsApp|WordPress|TikTok|OneDrive|SharePoint|PowerPoint|DevOps|PostgreSQL|MongoDB|MySQL"
                     r"|kWh|kW|kB|MB|GB|dB|mL|mAh|pH|(?:Node|Next|Nuxt|Vue|D3|Express|Ember|Backbone)\.js)\b")
_BLOCKING_KINDS = frozenset({"file-path", "code-symbol"})
_LENIENT_PRIORITIES = frozenset({"should", "may", "could"})


def _scan_table(spec_text: str) -> tuple[dict[str, str], set[str], dict[str, str]]:
    """``({fr id: priority, lower-case}, {retired fr ids}, {fr id: Name cell})`` from the requirement tables of one spec."""
    priority: dict[str, str] = {}
    names: dict[str, str] = {}
    removed: set[str] = set()
    cols: dict[str, int] = {}
    in_removed = False
    for line in (spec_text or "").splitlines():
        if line.startswith("#"):
            in_removed = "removed" in line.lower()
            cols = {}
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0].lower() == "id":
            cols = {c.lower(): i for i, c in enumerate(cells)}
        elif re.fullmatch(r"FR-\d+\.\d+", cells[0]):
            if in_removed:
                removed.add(cells[0])
            else:
                if "priority" in cols and cols["priority"] < len(cells):
                    priority[cells[0]] = re.sub(r"[`*_\s]", "", cells[cols["priority"]]).lower()
                if "name" in cols and cols["name"] < len(cells):
                    names[cells[0]] = cells[cols["name"]]
    return priority, removed, names


def check_spec(spec_text: str) -> list[dict]:
    """``[{"fr", "problems": [...], "prompts": [...], "needs_capability_test": bool}]`` for every FR with a problem or a prompt.

    ``problems`` block; ``prompts`` do not. An empty list = nothing to report.
    """
    acs, frs = parse_catalog(spec_text)
    if not frs:  # empty, blank, or text with nothing readable must never pass as "every requirement is fine"
        return [{"fr": "(whole spec)", "problems": ["no requirement this check can read"], "prompts": [], "needs_capability_test": False}]
    priority, removed, names = _scan_table(spec_text)
    by_fr: dict[str, list[tuple[str, str]]] = {}
    for ac_id, line in acs.items():
        by_fr.setdefault(ac_id.rsplit(".AC", 1)[0], []).append((ac_id.rsplit(".", 1)[1], _MARKUP.sub("", line).strip()))
    out = []
    for fr, title in frs.items():
        if fr in removed:
            continue
        problems: list[str] = []
        prompts: list[str] = []
        criteria = by_fr.get(fr, [])
        if not criteria and priority.get(fr, "") not in _LENIENT_PRIORITIES:
            problems.append("no acceptance criteria (required for a Must requirement, or when the priority cannot be read as Should/May)")
        for ac, text in criteria:
            found = violations(_BRANDS.sub("Brand", text))
            hard = [k for k in found if k in _BLOCKING_KINDS]
            if hard:
                problems.append(f"{ac}: implementation detail ({', '.join(hard)})")
            if [k for k in found if k not in _BLOCKING_KINDS]:
                prompts.append(f"{ac}: mentions {', '.join(k for k in found if k not in _BLOCKING_KINDS)} - keep the how out of the criterion")
            if not is_well_formed_criterion(text):
                prompts.append(f"{ac}: not in Given/when/then form (fine for a checkbox criterion or a settlement criterion; check it is one testable assertion)")
        title = names.get(fr) or title
        joined = bool(title) and bool(_JOINS.search(f" {title} "))
        if joined:
            prompts.append("name joins two capabilities with 'and': apply the capability test (one plain sentence without 'and' per group)")
        if problems or prompts:
            out.append({"fr": fr, "problems": problems, "prompts": prompts, "needs_capability_test": joined})
    return out

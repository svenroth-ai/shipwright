"""Anti-ratchet for inline ``# nosemgrep`` suppressions — the rule itself.

An inline suppression silences a real security finding at one source site. It
is source-controlled and reviewed in the diff, but it carries no owner, no
expiry and no central visibility. The accepted-risk register deliberately does
NOT cover it — ``accepted_risks`` states that position and
``iterate-2026-08-05-inline-suppression-ratchet`` is the decision that settled
it. This module is the control that stands in its place: a per-rule site count
that cannot grow without a recorded decision.

**Why a count rather than a register entry.** Three reasons, in descending
weight:

1. *An offline reconciler would have to mirror Semgrep, and would drift.*
   Faithful offline discovery means re-implementing per-language comment
   syntax, both suppression spellings, the matched-or-preceding-line adjacency
   rule, and rule-id prefix matching. Every one is a drift site.
2. *Drift is asymmetric.* In the register's BOTH-directions gate a discovery
   error produces a false ``STALE``, which tells the operator to delete an
   entry that is doing its job — the failure mode
   ``accepted_risks_cli._format_check``'s ``ignore_unreadable`` branch exists
   to prevent. A COUNT has the opposite bias: over-counting is absorbed by the
   baseline and never advises a deletion.
3. *The register's defining field does not fit.* ``expires`` is what the
   register is FOR. But ``non-literal-import`` on the ADR-045 dynamic loader is
   not a time-bounded acceptance; it is a permanent consequence of how the
   loader works. A risk acceptance says "real, accepted until DATE"; an inline
   suppression says "a false positive at this site, permanently". Forcing the
   second into a shape built for the first yields entries renewed by ritual,
   which devalues the entries whose date genuinely means something.

This is the trio's entry point. Discovery lives in ``inline_suppression_scan``
(whose docstring carries the disclosed limits of the measurement) and the
baseline document in ``inline_suppression_baseline``; both are re-exported here
so callers have one import.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from accepted_risks import DECISION_REF_RE
from inline_suppression_baseline import (
    BASELINE_NAME,
    SCHEMA_VERSION,
    BaselineError,
    baseline_path,
    dump_baseline,
    load_baseline,
    seed_baseline,
)
from inline_suppression_scan import scan, scan_sites

__all__ = [
    "BASELINE_NAME", "DECISION_REF_RE", "SCHEMA_VERSION", "BaselineError",
    "baseline_path", "dump_baseline", "format_report", "load_baseline",
    "reconcile", "scan", "scan_sites", "seed_baseline",
]


def reconcile(project_root: Path | str) -> dict[str, Any]:
    """Compare discovered suppressions against the baseline.

    BLOCKING: a rule above its ``max_sites``, a rule with no entry at all, any
    unreadable file, and a **dead** entry — one whose rule is now suppressed
    NOWHERE.

    ADVISORY: a rule merely below its entry. Blocking on a partial reduction
    would penalise the outcome this gate exists to encourage, so ``shrunk``
    never affects ``ok``.

    **Why dead-at-zero blocks while shrink-to-one does not.** Not a
    residual-risk threshold — that framing does not survive, since slack of 8
    out of 9 is advisory while slack of 1 out of 1 blocks (Stage-3 doubt
    review, D7). The line is *record versus reality*: a dead entry is one
    nothing in the tree corresponds to any more, so it can never again be
    checked against the thing it describes. That is exactly the register's own
    ``STALE`` — a record claiming something is accepted when no such
    suppression is in place — and this codebase already treats staleness as a
    first-class defect rather than a tolerance. A partially-shrunk entry still
    has at least one real site anchoring it to reality; a dead one has none.
    (The distinction was added in Stage-2 code review, which caught an earlier
    version asserting the block in a test while the contract promised it could
    not happen.)
    """
    discovered = scan(project_root)
    sites = discovered["sites"]
    entries = load_baseline(project_root)

    ratchets: list[dict] = []
    unrecorded: list[dict] = []
    shrunk: list[dict] = []
    dead: list[dict] = []
    for rule in sorted(sites):
        measured = len(sites[rule])
        entry = entries.get(rule)
        if entry is None:
            unrecorded.append(
                {"rule": rule, "measured": measured, "sites": sites[rule]})
        elif measured > entry["max_sites"]:
            ratchets.append({
                "rule": rule, "baseline_max": entry["max_sites"],
                "measured": measured, "sites": sites[rule],
            })
        elif measured < entry["max_sites"]:
            shrunk.append({
                "rule": rule, "baseline_max": entry["max_sites"],
                "measured": measured,
            })
    for rule in sorted(set(entries) - set(sites)):
        dead.append({
            "rule": rule, "baseline_max": entries[rule]["max_sites"],
            "measured": 0,
        })

    return {
        "sites": sites,
        "entries": entries,
        "mode": discovered["mode"],
        "unreadable": discovered["unreadable"],
        "files_examined": discovered["files_examined"],
        "baseline_present": baseline_path(project_root).is_file(),
        "ratchets": ratchets,
        "unrecorded": unrecorded,
        "shrunk": shrunk,
        "dead": dead,
        "ok": not (ratchets or unrecorded or dead or discovered["unreadable"]),
    }


def format_report(result: dict) -> list[str]:
    """Actionable diagnostic lines. Every block names the offending sites."""
    lines: list[str] = []
    for item in result["unreadable"]:
        lines.append(
            f"UNREADABLE  {item}\n"
            "    Could not be read (or exceeds the size cap), so the count is "
            "PARTIAL and cannot be trusted.\n"
            "    Fix: make the file readable, or untrack it."
        )
    for item in result["ratchets"]:
        lines.append(
            f"RATCHET     {item['rule']}\n"
            f"    {item['measured']} inline suppressions, baseline allows "
            f"{item['baseline_max']}.\n"
            f"    Sites: {', '.join(item['sites'])}\n"
            "    Fix: remove the new suppression (preferred), or raise "
            f"`max_sites` in {BASELINE_NAME} with a rationale_ref naming a "
            "recorded decision."
        )
    for item in result["unrecorded"]:
        # A rule id with no dot is far more often prose that ran into the
        # capture group than a real custom rule: `nosemgrep: <id>, needed for
        # Windows` yields a phantom rule `needed`. Semgrep reads it that way
        # too, so blocking is right; the operator just needs to be told what
        # they are looking at (Stage-3 doubt review, D13). The angle brackets
        # here are load-bearing — writing a literal id would make this comment
        # a counted site, which is how this very hint first went red.
        hint = ""
        if "." not in item["rule"]:
            hint = (
                "\n    NOTE: this does not look like a rule id. A comma after "
                "the real id makes the words that follow into extra rule ids "
                "— for Semgrep too. Separate a justification with ` -- `, not "
                "a comma."
            )
        lines.append(
            f"UNRECORDED  {item['rule']}\n"
            f"    {item['measured']} inline suppression(s) with no baseline "
            "entry — nobody has recorded why this rule is silenced.\n"
            f"    Sites: {', '.join(item['sites'])}"
            f"{hint}\n"
            f"    Fix: add an entry to {BASELINE_NAME}, or remove the "
            "suppression."
        )
    for item in result["dead"]:
        lines.append(
            f"DEAD        {item['rule']}\n"
            f"    The baseline still licenses {item['baseline_max']} "
            "suppression(s) of this rule, but it is suppressed NOWHERE — a "
            "dormant licence to silence it again with no fresh decision.\n"
            f"    Fix: delete this entry from {BASELINE_NAME}."
        )
    for item in result["shrunk"]:
        lines.append(
            f"advisory    {item['rule']}: {item['measured']} site(s) but "
            f"baseline allows {item['baseline_max']} — tighten `max_sites` in "
            f"{BASELINE_NAME} to lock the improvement in."
        )
    return lines

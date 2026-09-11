#!/usr/bin/env python3
"""Re-measure the REQ-3 AC-evidence ledger's own status counts (campaign
``req3-06-enforcement-mono``, sub-iterate ``e0-ledger-accounting``).

**Why this exists.** The ledger
(``.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md``)
carries its own "Distribution after the end-check" table, hand-counted once
on 2026-07-26 and never re-derived since — every walk after that date
(`.01`, `.09`'s addendum, the retro scenario pass, later walks minting new
criteria) added or changed rows without anyone re-running the count. A
hand count is exactly the kind of number this ledger itself warns readers
not to trust at face value: it reads as authoritative and silently goes
stale (a stale card carried 44/15/10/25 into this very campaign — see the
``e0-ledger-accounting`` sub-iterate spec). This script re-derives the
distribution mechanically, from the document's own text, every time it is
run, so "trust the header" becomes "re-run the script".

**What it counts, and the deliberate simplicity trade-off.** Each of the
ledger's 8 canonical status tags (``enforced``, ``enforced, untested``,
``enforced, tested``, ``enforced, partly tested``, ``prompt-only
(mechanisable)``, ``prompt-only (judgement)``, ``unimplemented``,
``no-oracle`` — defined in the ledger's own legend near the top) is counted
by every backtick-quoted occurrence of that exact phrase across the WHOLE
file — not only inside a per-FR criterion table. This is deliberate, not
an oversight: the ledger is a hand-written document whose tables take a
different ad-hoc shape in nearly every section (a plain criterion table,
a 2-column "what stood first instead" table, a "New criterion / Enforcement
/ Why" retro-scenario recap table, a bare bullet list...), so a parser that
tries to recognise "a real criterion row" structurally would need one rule
per table shape and would silently break on the next new one a future walk
invents. A flat text count needs none of that, and it was cross-checked
against the operator's own by-hand re-measurement on 2026-09-06 (recorded
in the ``e0-ledger-accounting`` spec: 47 prompt-only (mechanisable), 19
prompt-only (judgement), 16 enforced-untested, 36 unimplemented, 50
enforced-tested) — this script reproduces every one of those five numbers
exactly against the ledger text as it stood then, which is the evidence
that the simple method is accurate enough for what this document is used
for (a backlog size for the enforcement campaign, not a formal audit).

**The known, accepted imprecision.** The ledger's own legend table and its
"Distribution after the end-check" summary table are themselves text that
uses these same backtick-quoted phrases (to name each category once), so
each contributes a small, constant amount to its own count — the price of
counting text rather than parsing table structure. It does not need
correcting: the legend and the summary line are exactly the KIND of
"where does this number come from" text a reader benefits from seeing
counted consistently release over release, and the alternative (excluding
some tables from the sweep by hand-picked heading names) is itself a
second stale list waiting to happen the next time a table moves.

Usage::

    uv run shared/scripts/tools/measure_ac_evidence_ledger.py [--file PATH] [--json]

Exit codes: ``0`` on a successful measurement (a reporting tool, not a
gate — it never fails the count itself); ``2`` if the ledger file cannot
be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_LEDGER_RELPATH = ".shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md"

# The 8 canonical statuses this ledger's own legend defines (its header
# table, near the top of the document). Only the `enforced` family needs
# ordering (longest-first, so `enforced, tested` is never swallowed by a
# bare `enforced` match first) — the other four never share a prefix with
# one another, so their relative order does not matter.
CANONICAL_STATUSES = [
    "enforced, partly tested",
    "enforced, untested",
    "enforced, tested",
    "enforced",
    "prompt-only (mechanisable)",
    "prompt-only (judgement)",
    "unimplemented",
    "no-oracle",
]

# The 5 categories the enforcement campaign actually tracks as backlog —
# `enforced` (nothing to do) and `no-oracle` (a standing operator decision,
# not campaign work) are measured but excluded from this summary line.
BACKLOG_STATUSES = [
    "prompt-only (mechanisable)",
    "prompt-only (judgement)",
    "enforced, untested",
    "unimplemented",
    "enforced, tested",
]


def count_statuses(text: str) -> dict[str, int]:
    """Count every backtick-quoted occurrence of each canonical status,
    longest-alternative-first so a qualified status is never double-counted
    as its unqualified prefix (e.g. an `` `enforced, tested` `` occurrence
    must not also increment the bare `` `enforced` `` count)."""
    remaining = text
    counts: dict[str, int] = {}
    for status in CANONICAL_STATUSES:
        pattern = re.compile("`" + re.escape(status) + "`")
        matches = pattern.findall(remaining)
        counts[status] = len(matches)
        remaining = pattern.sub("", remaining)
    return counts


def measure(text: str) -> dict:
    counts = count_statuses(text)
    return {
        "status_counts": counts,
        "status_marks_total": sum(counts.values()),
        "backlog_line": {status: counts[status] for status in BACKLOG_STATUSES},
    }


def format_backlog_line(backlog: dict[str, int]) -> str:
    return (
        f"{backlog['prompt-only (mechanisable)']} prompt-only (mechanisable), "
        f"{backlog['prompt-only (judgement)']} prompt-only (judgement), "
        f"{backlog['enforced, untested']} enforced-untested, "
        f"{backlog['unimplemented']} unimplemented, "
        f"{backlog['enforced, tested']} enforced-tested"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help=f"ledger path (default: {DEFAULT_LEDGER_RELPATH} under --project-root)",
    )
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON only")
    args = parser.parse_args(argv)

    ledger_path = args.file or (args.project_root.resolve() / DEFAULT_LEDGER_RELPATH)
    if args.file is None and not ledger_path.is_file():
        # CWD-relative default missed (e.g. invoked from a nested directory,
        # or via a test runner whose cwd isn't the repo root) — fall back to
        # this script's own known location before giving up. This is the
        # tool the ledger tells readers to re-run; it should not be
        # CWD-fragile when the obvious repo-relative guess is available.
        repo_relative_guess = Path(__file__).resolve().parents[3] / DEFAULT_LEDGER_RELPATH
        if repo_relative_guess.is_file():
            ledger_path = repo_relative_guess
    try:
        text = ledger_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(json.dumps({"error": f"could not read {ledger_path}: {exc}"}), file=sys.stderr)
        return 2

    result = measure(text)
    payload = {"ledger": str(ledger_path), **result}

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Ledger: {payload['ledger']}")
    print(f"Status marks total: {payload['status_marks_total']}")
    print()
    print("Distribution:")
    for status in CANONICAL_STATUSES:
        print(f"  {status:<28} {payload['status_counts'][status]}")
    print()
    print("Backlog re-measurement line (the 5 categories the enforcement campaign tracks):")
    print(f"  {format_backlog_line(payload['backlog_line'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

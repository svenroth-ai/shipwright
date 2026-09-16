#!/usr/bin/env python3
"""Re-measure the REQ-3 AC-evidence ledger's own status counts (campaign
``req3-06-enforcement-mono``, sub-iterate ``e0-ledger-accounting``).

**Why this exists.** The ledger
(``.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md``)
carries its own status distribution, hand-counted once and never re-derived
since — a hand count is exactly the kind of number this ledger itself warns
readers not to trust at face value: it reads as authoritative and silently
goes stale (see the ``e0-ledger-accounting`` sub-iterate spec). This script
re-derives the distribution mechanically, from the document's own text,
every time it is run, so "trust the header" becomes "re-run the script".

**What it counts, and why it is restricted to table rows.** Each of the
ledger's 8 canonical status tags (``enforced``, ``enforced, untested``,
``enforced, tested``, ``enforced, partly tested``, ``prompt-only
(mechanisable)``, ``prompt-only (judgement)``, ``unimplemented``,
``no-oracle`` — defined in the ledger's own legend near the top) is counted
by every backtick-quoted occurrence of that exact phrase, but **only on
lines that are themselves markdown table rows** (a line whose first
non-whitespace character is ``|``, outside a fenced code block). The
ledger's tables take a different ad-hoc shape in nearly every section, so
this script does not try to recognise "a real criterion row" by column
position or table shape — it only asks "is this line part of a table at
all". That restriction is enough to stop a status name mentioned in
running prose (the ledger is prose-heavy by design) from silently
inflating the count.

**Two tables are explicitly excluded even though they ARE table rows: the
vocabulary legend (near the top) and the "Distribution after the end-check"
historical summary table.** Both name every canonical status once, so
without this exclusion they would still inflate every count by a small,
constant amount. Both share one structural trait no real per-FR criterion
table has: their **first** column is itself headed ``Status`` (every real
criterion table puts ``Status`` in a later column). A table block is
excluded when its header cell is structurally "status"
(``_table_header_first_cell`` splits on ``|`` and compares stripped,
casefolded text — not a literal string prefix, so a whitespace variant of
the same header is still recognised); nothing else is special-cased. Every
excluded block is recorded (line number + header text) in ``measure()``'s
``excluded_tables`` output, so a reader can verify only the legend and the
summary were dropped rather than trusting the rule silently. The exclusion
is block-scoped: a blank line (or any non-table line) above the legend is
what keeps it its own block, separate from a preceding criterion table —
if a future edit ever glued the two together with no separator, the merged
block's header would no longer read "status" and the legend would stop
being excluded (the ``excluded_tables`` count dropping below 2 is the
observable symptom).

**What this does not fix: a status backtick-quoted in a non-status column
of a real table row still counts.** Restricting to table rows stops prose
*outside* tables from inflating the count; it does not restrict *inside* a
row to only the status cell — an "Evidence / gap" column can itself narrate
a status the row no longer holds, and that mention still counts. This is
the same, already-tested, already-documented trade-off
`test_split_row_contributes_to_both_halves` pins for the opposite case (a
row legitimately naming two statuses because it splits a criterion in
two) — the script cannot distinguish the two without reading comprehension.
Column-position parsing (count only the literal "Status"-headed column,
per row) was considered and rejected: at least one real, already-counted
table in the live ledger headers its status column ``Enforcement``, not
``Status``, so column-name matching would silently *undercount* real
criterion rows on a table shape already in use.

**Fenced code blocks are skipped.** A ` ``` ` toggle excludes everything
between fence markers from the table-row sweep, so a pipe-prefixed example
table inside a documentation code sample is never miscounted as a real
row. An unterminated fence (an odd number of ` ``` ` markers) is treated as
open through end-of-file, so everything after it is silently excluded too
— `measure()`'s ``unterminated_fence`` flag reports this rather than
letting a hand-edit mistake masquerade as a clean, if lower, count.

**Historical numbers were measured differently and are not retroactively
rewritten** — the same rule ADR numbering already follows (never renumber
retroactively). Full rationale, the 2026-09-12 incident this fix closes,
and the list of documents whose numbers predate it and are not touched:
the ``iterate-2026-09-16-ac-ledger-status-cell-counting`` spec.

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


def _table_header_first_cell(line: str) -> str:
    """The first cell of a markdown table row, stripped and casefolded, e.g.
    ``"| Status | Rows |"`` -> ``"status"``, ``"|  Status  |Rows|"`` ->
    ``"status"``. Structural (split on `|`), not a literal-prefix match, so
    a whitespace variant of the legend/summary header is still recognised."""
    return line.strip().strip("|").split("|")[0].strip().casefold()


class _TableRowFilter:
    """Result of filtering `text` down to its markdown table rows.

    `row_text`: the table-row-only text, ready for `count_statuses`'s regex
    sweep. `excluded`: every dropped block's 1-indexed line number + header
    text, surfaced as `measure()`'s `excluded_tables` — see `_table_row_text`.
    `unterminated_fence`: whether the text ended with an odd number of
    ` ``` ` markers, i.e. a fence that was still open at EOF (everything
    after it was silently excluded as a precaution, since content inside an
    unclosed fence cannot be told apart from real prose)."""

    def __init__(self, row_text: str, excluded: list[tuple[int, str]], unterminated_fence: bool) -> None:
        self.row_text = row_text
        self.excluded = excluded
        self.unterminated_fence = unterminated_fence


def _table_row_text(text: str) -> _TableRowFilter:
    """Filter `text` down to its markdown table rows.

    A "table row" is a line whose first non-whitespace character is `|`,
    outside a fenced code block (a ` ``` ` toggle skips fence contents, so a
    pipe-prefixed example line inside a code sample is never read as a real
    row). A contiguous run of such lines is one block; a block is entirely
    excluded when its header (first line)'s first cell is structurally
    "status" (see `_table_header_first_cell`) — the shape of both the
    vocabulary legend and the historical distribution summary, and of no
    real per-FR criterion table (see the module docstring's "Two tables are
    explicitly excluded" section)."""
    lines = text.splitlines()
    kept: list[str] = []
    excluded: list[tuple[int, str]] = []
    in_fence = False
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence or not line.lstrip().startswith("|"):
            i += 1
            continue
        # Start of a table block: walk it forward while rows stay contiguous.
        block_start = i
        j = i
        while j < n and lines[j].lstrip().startswith("|"):
            j += 1
        block = lines[block_start:j]
        if _table_header_first_cell(block[0]) == "status":
            excluded.append((block_start + 1, block[0].strip()))
        else:
            kept.extend(block)
        i = j
    return _TableRowFilter("\n".join(kept), excluded, unterminated_fence=in_fence)


def count_statuses(text: str) -> dict[str, int]:
    """Count every backtick-quoted occurrence of each canonical status,
    restricted to markdown table rows (excluding the legend and the
    historical distribution summary — see the module docstring) and
    longest-alternative-first so a qualified status is never double-counted
    as its unqualified prefix (e.g. an `` `enforced, tested` `` occurrence
    must not also increment the bare `` `enforced` `` count). This does NOT
    restrict further to a row's own status *cell* — a different column of a
    real table row (a rationale, an "Evidence / gap" note) that itself
    backtick-quotes a status still counts; see the module docstring's
    "What this does not fix" section."""
    remaining = _table_row_text(text).row_text
    counts: dict[str, int] = {}
    for status in CANONICAL_STATUSES:
        pattern = re.compile("`" + re.escape(status) + "`")
        matches = pattern.findall(remaining)
        counts[status] = len(matches)
        remaining = pattern.sub("", remaining)
    return counts


def measure(text: str) -> dict:
    # `_table_row_text` is walked twice — once here, once inside
    # `count_statuses` — rather than threading its result through. Both
    # calls are pure and cheap (a single O(document length) pass over a
    # ~2000-line file), and keeping `count_statuses` a self-contained
    # `text -> counts` function is what lets its unit tests call it
    # directly without also asserting on the filter's other outputs.
    counts = count_statuses(text)
    row_filter = _table_row_text(text)
    return {
        "status_counts": counts,
        "status_marks_total": sum(counts.values()),
        "backlog_line": {status: counts[status] for status in BACKLOG_STATUSES},
        "excluded_tables": [{"line": line_no, "header": header} for line_no, header in row_filter.excluded],
        "unterminated_fence": row_filter.unterminated_fence,
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
    print()
    print("Excluded tables (Status-first header — legend/summary, not criterion rows):")
    for excluded in payload["excluded_tables"]:
        print(f"  line {excluded['line']}: {excluded['header']}")
    if payload["unterminated_fence"]:
        print()
        print(
            "WARNING: an unterminated ``` fence was found (odd number of markers) — "
            "everything after it was excluded from the count as a precaution. "
            "Check for a missing closing ``` in the ledger."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

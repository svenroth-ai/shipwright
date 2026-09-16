#!/usr/bin/env python3
"""Re-measure the REQ-3 AC-evidence ledger's own status counts (campaign
``req3-06-enforcement-mono``, sub-iterate ``e0-ledger-accounting``).

Counts every backtick-quoted occurrence of each of the ledger's 8 canonical
status tags, restricted to markdown table rows (a line whose first
non-whitespace character is ``|``, outside a fenced code block) — not the
whole document, so a status name mentioned in prose never inflates the count.

Two table blocks are excluded even though they ARE table rows: the
vocabulary legend and the historical distribution summary. Both share one
trait no real per-FR criterion table has — their **first** column is itself
headed ``Status`` — so a block is excluded when its header cell is
structurally "status" (``_table_header_first_cell``, whitespace-tolerant,
not a literal prefix). Every excluded block is recorded in ``measure()``'s
``excluded_tables`` output for audit.

**What this does not fix:** a status backtick-quoted in a non-status column
of a real row still counts — restricting to table rows stops prose *outside*
tables, not columns *inside* a row. Column-position parsing was considered
and rejected: a real table in the live ledger headers its status column
``Enforcement``, not ``Status``, so column-name matching would undercount it.

Fenced code blocks are skipped (backtick or tilde, CommonMark fence-matching:
<=3-space indent, same character, closing run length >= the opener's, no
info string on the closing line) so a pipe-prefixed example table inside one
is never miscounted as a real row. An unterminated fence excludes everything
after it, reported via ``measure()``'s ``unterminated_fence`` flag.

Historical numbers were measured differently and are **not** retroactively
rewritten (never renumber retroactively, same as ADR numbering). Full
rationale, the 2026-09-12 incident this fix closes, and the list of
documents whose numbers predate it: the
``iterate-2026-09-16-ac-ledger-status-cell-counting`` spec.

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


_FENCE_CHARS = ("`", "~")

# CommonMark: a 4+-space-indented marker is indented-code, not a fence (CI PR-review).
_FENCE_MAX_INDENT = 3


def _fence_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _fence_run(line: str) -> tuple[str, int] | None:
    """(char, run_length) of a leading, <=3-space-indented backtick/tilde
    run of length >= 3, if any: "```python" -> ("`", 3); 4-space indent -> None."""
    if _fence_indent(line) > _FENCE_MAX_INDENT:
        return None
    stripped = line.lstrip()
    if not stripped or stripped[0] not in _FENCE_CHARS:
        return None
    char = stripped[0]
    run = len(stripped) - len(stripped.lstrip(char))
    return (char, run) if run >= 3 else None


def _fence_closes(line: str, char: str, min_run: int) -> bool:
    """True if `line` closes a fence opened with `char` at length `min_run`:
    indented at most 3 spaces, same character, run length >= the opener's,
    nothing but whitespace after (an info string like "```python" opens but
    cannot close a fence)."""
    if _fence_indent(line) > _FENCE_MAX_INDENT:
        return False
    stripped = line.lstrip()
    run = len(stripped) - len(stripped.lstrip(char))
    return run >= min_run and stripped[run:].strip() == ""


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
    `unterminated_fence`: whether the text ended with an unclosed backtick
    or tilde fence still open at EOF (everything after it was silently
    excluded as a precaution, since content inside an unclosed fence
    cannot be told apart from real prose)."""

    def __init__(self, row_text: str, excluded: list[tuple[int, str]], unterminated_fence: bool) -> None:
        self.row_text = row_text
        self.excluded = excluded
        self.unterminated_fence = unterminated_fence


def _table_row_text(text: str) -> _TableRowFilter:
    """Filter `text` down to its markdown table rows.

    A "table row" is a line whose first non-whitespace character is `|`,
    outside a fenced code block (backtick or tilde). A contiguous run of
    such lines is one block; a block is entirely
    excluded when its header (first line)'s first cell is structurally
    "status" (see `_table_header_first_cell`) — the shape of both the
    vocabulary legend and the historical distribution summary, and of no
    real per-FR criterion table (see the module docstring's "Two tables are
    explicitly excluded" section)."""
    lines = text.splitlines()
    kept: list[str] = []
    excluded: list[tuple[int, str]] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if in_fence:
            if _fence_closes(line, fence_char, fence_len):
                in_fence = False
            i += 1
            continue
        opened = _fence_run(line)
        if opened is not None:
            fence_char, fence_len = opened
            in_fence = True
            i += 1
            continue
        if not line.lstrip().startswith("|"):
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
            "WARNING: an unterminated ``` or ~~~ fence was found — everything "
            "after it was excluded from the count as a precaution. Check for "
            "a missing closing marker in the ledger."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The ONE header-driven reader for ``spec.md`` functional-requirement tables.

Campaign "Requirements Catalog", sub-iterate S4. Five parsers used to read this
one table shape — two positional (``drift_parsers.parse_fr_table``,
``rtm.collect_requirements``, sharing a byte-identical regex and two
semantic-clone removed-section loops that nothing kept in sync) and three
header-driven with three different strictnesses. They disagreed on seven axes,
and four documented false verdicts (FV-1, FV-3, FV-4, FV-5) were consequences of
that divergence. This module is the single implementation; the five callers keep
their own return TYPES — those are genuinely different contracts — but none of
them parses any more.

**ADR-031 is revised, not extended.** It rejected header-driven parsing as
"over-engineered for two known formats with stable column orders". There are five
formats, their column orders are not stable, and ADR-048 records a brownfield RTM
reporting "Traceability coverage 0%" because the positional regex never matched
the 6-column adopt shape. The prediction is falsified.

The convergence rules, each of which used to have two or three answers:

1. **Id strictness** — ``requirement_model.CANONICAL_FR_RE`` (``FR-XX.YY``), a
   FULL match of the trimmed cell. Not a preference: manifest schema v3 derives
   a requirement's namespace from the id's group digits, so only the two-digit
   form makes that derivation total. ``FR-7`` / ``FR-1.1`` are legal spec
   HEADING ids but never canonical row ids — and are RECORDED when rejected.
2. **Column selection is by NAME**, never by position. A row carrying more cells
   than its header declares can no longer shift the body column (FV-3 — live
   wrong text in a shipped RTM).
3. **The column map persists across headings.** Resetting at every heading
   dropped every FR row under a later heading (FV-5). What ends a requirements
   table is another TABLE, not a title — see rule 8.
4. **An unrecognised priority is coerced, not fatal** (``Must``, the coercion
   that makes an audit louder rather than blinder). Dropping a requirement over
   a typo is the silent-loss class this campaign exists to remove.
5. **An escaped pipe is content, not a cell boundary.** Splitting and
   unescaping are one left-to-right pass in ``_fr_table_cells.split_cells``,
   the exact inverse of the ``markdown_table.escape_cell`` producer — see that
   module for the two defects a lookbehind-plus-replace version had, both found
   by a round-trip probe rather than by reading.
6. **A row is recognised by a leading pipe after stripping**, and a missing
   closing pipe does not drop it. An anchored ``^\\|`` rejects a legitimately
   indented GFM table.
7. **``## FR-Fold-Map`` lines are always skipped.** Under rule 4 this is
   load-bearing rather than cosmetic: without it, coercion would resurrect every
   folded alias id as a live requirement demanding its own coverage.
8. **A requirement row must be GOVERNED**: under a header naming a Priority
   column, and wide enough to reach it. No headerless positional fallback. This
   stops a coverage table keyed by FR id yielding requirements — rules 3, 4 and
   the absence of a width floor composed to admit one. See ``read_fr_rows``.

**Nothing is dropped silently.** Every row the reader declines is recorded via
the optional ``rejects`` accumulator, with the reason.

Pure: no I/O, no globals mutated, no exit-code semantics. Callers read files.
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

_SIBLINGS: dict[str, object] = {}


def _sibling(name: str):
    """Import a ``shared/scripts/lib`` sibling however THIS module was loaded.

    Three load styles reach this module in production (ADR-045): flat
    (``import fr_table_reader`` with ``shared/scripts/lib`` on the path),
    as a package member (``lib.fr_table_reader``, via the collectors'
    ``_lib_loader``), and by file location under a sentinel name (via
    ``audit_adapters.load_shared_lib``, which is how Group I reaches shared
    code). A bare relative import works only in the second; a bare flat import
    only in the first. Resolving per load style is what makes ONE reader usable
    from all five call sites — the alternative is five copies, which is the
    defect this module removes.

    Resolved EAGERLY, at import time, and never at call time. Under the
    collectors' ``_lib_loader`` this module is imported while ``sys.modules
    ['lib']`` is temporarily bound to SHARED, and that binding is restored to
    the caller's own ``lib`` on the way out — so a lazy ``import_module
    (".requirement_model", "lib")`` would resolve against the compliance-local
    package and raise. Same trap ADR-045 documents; the fix is the timing.
    """
    if (mod := _SIBLINGS.get(name)) is not None:
        return mod
    package = __package__ or ""
    if package:
        mod = importlib.import_module(f".{name}", package)
    else:
        lib_dir = str(Path(__file__).resolve().parent)
        added = lib_dir not in sys.path
        if added:
            sys.path.insert(0, lib_dir)
        try:
            # First-party hardcoded module identifiers only; no untrusted input.
            # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
            mod = importlib.import_module(name)
        finally:
            if added:
                sys.path.remove(lib_dir)
    _SIBLINGS[name] = mod
    return mod


CANONICAL_FR_RE = _sibling("requirement_model").CANONICAL_FR_RE
_fold_map_line_numbers = _sibling("fr_fold_map").fold_map_line_numbers
split_cells = _sibling("_fr_table_cells").split_cells

FrTableRow = _sibling("_fr_table_row").FrTableRow

_cols = _sibling("_fr_table_columns")
BASIS_COLS = _cols.BASIS_COLS
DEFAULT_PRIORITY = _cols.DEFAULT_PRIORITY
LAYERS_COLS = _cols.LAYERS_COLS
NAME_COLS = _cols.NAME_COLS
PRIORITIES = _cols.PRIORITIES
PRIORITY_COLS = _cols.PRIORITY_COLS
TITLE_COLS = _cols.TITLE_COLS
normalise_priority = _cols.normalise_priority
_basis_cell = _cols.basis_cell
_header_map = _cols.header_map
_is_separator_row = _cols.is_separator_row
_layers_cell = _cols.layers_cell
_pick = _cols.pick

_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
_REMOVED_HEADING = "removed requirements"

#: The old loose tier. Used only to tell a malformed requirement row apart from
#: a table header, and to name what was rejected — never to accept a row.
_LOOSE_FR_RE = re.compile(r"^FR-[\d.]+$")


def read_fr_rows(content: str, *, rejects: list | None = None) -> list[FrTableRow]:
    """Read every FR row — active AND removed — out of a ``spec.md`` body.

    Callers that want only live requirements filter on ``status``; the removed
    rows are load-bearing for orphan categorisation and for the rule that a
    retired FR number is never reused, so they are never dropped here.

    ``rejects`` (optional out-accumulator, mirroring ``_requirement_parse``'s
    ``invalid_layers``) collects every row this reader declined to treat as a
    requirement, with the reason. **Nothing is dropped silently.** Three reasons
    exist, and each corresponds to one of the guards below:

    * ``non_canonical_id`` — the first cell looks like an FR id but is not the
      canonical ``FR-XX.YY`` form. This is the one that matters in practice:
      ``generate_adoption_artifacts`` emits ``f"FR-01.{i:02d}"`` with no cap on
      ``i``, so an adopted repo with more than 99 detected routes emits
      ``FR-01.100`` — accepted by the old loose regex, rejected by the canonical
      tier, and until this accumulator existed it left the RTM silently.
    * ``no_governing_header`` — a canonical id under no priority-bearing header.
    * ``row_narrower_than_header`` — a canonical id in a row too short to reach
      the Priority column its own header declares.

    **Why the last two guards exist (the composition route — ADR-107).** A
    surviving column map (rule 3), a coerced priority (rule 4) and no width
    floor are each defensible and compose into a defect: a second, FR-id-keyed
    table under a later heading parsed as requirements, reaching
    ``build_requirement_index`` → ``DuplicateRequirementId``, which names the
    same file twice and says "renumber one of the two rows" — unactionable,
    because the second row is not a requirement. Every guard that independently
    blocked that route (a positional priority column, a three-cell floor, a
    reset at every heading) was removed by the same change that introduced this
    reader, so it had to be re-established deliberately, not inherited.
    """
    # A UTF-8 BOM is not whitespace to str.strip(), so a BOM'd first line does
    # not start with "|" and its table header is invisible — which, now that
    # there is no headerless fallback, silently costs the whole first table.
    # Caught by the BOM probe when rule C6 was withdrawn, not by reading.
    content = content.lstrip("﻿")
    fold_lines = _fold_map_line_numbers(content)

    rows: list[FrTableRow] = []
    colmap: dict[str, int] | None = None
    in_removed = False
    removed_level = 0

    def _reject(reason: str, cells: list[str], lineno: int) -> None:
        if rejects is not None:
            rejects.append({
                "id": cells[0], "reason": reason,
                "lineno": lineno, "raw": " | ".join(cells)[:200],
                # Whether a governing header had been recognised when this row
                # was declined (campaign S5). Without it a caller cannot tell
                # "no header names a Priority column" from "the header is fine,
                # the ids are not" — the two states Group I must report apart,
                # and the second is exactly the one rule 1's strict id tier
                # creates. `reason` alone cannot carry it: `non_canonical_id` is
                # decided BEFORE the map is consulted and so occurs under both.
                "header_seen": colmap is not None,
            })

    for lineno, line in enumerate(content.splitlines()):
        if lineno in fold_lines:
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            if heading.group(2).strip().lower().startswith(_REMOVED_HEADING):
                in_removed, removed_level = True, level
            elif in_removed and level <= removed_level:
                in_removed = False
            # The column map deliberately SURVIVES the heading (rule 3) — that
            # is the FV-5 fix. What ends a table is another TABLE, not a title.
            continue

        if not line.strip().startswith("|"):
            continue
        cells = split_cells(line)
        if not cells or _is_separator_row(cells):
            continue

        if not CANONICAL_FR_RE.match(cells[0]):
            if _LOOSE_FR_RE.match(cells[0]):
                # An FR-shaped id that is not canonical is a malformed
                # REQUIREMENT row, never a header. Treating it as one would let
                # a single `FR-1.1` invalidate the map and drop every row after.
                _reject("non_canonical_id", cells, lineno)
            elif (header := _header_map(cells)) is not None:
                colmap = header
            else:
                # A table row that is not a requirement and names no Priority
                # column: we have left the requirements table. Invalidating the
                # map is what stops a coverage table's FR-keyed rows from being
                # read as requirements, at ANY row width.
                colmap = None
            continue

        if colmap is None:
            _reject("no_governing_header", cells, lineno)
            continue
        if len(cells) <= colmap[PRIORITY_COLS[0]]:
            # The row cannot reach the Priority column its header declares, so
            # it does not fit the shape that header claims. Closes the variant
            # where the foreign table has no header row of its own and inherits
            # a stale map.
            _reject("row_narrower_than_header", cells, lineno)
            continue

        layers_cell, layers_named = _layers_cell(cells, colmap)
        basis_cell, basis_named = _basis_cell(cells, colmap)
        rows.append(FrTableRow(
            id=cells[0],
            name=_pick(cells, colmap, NAME_COLS),
            text=_pick(cells, colmap, TITLE_COLS),
            priority=normalise_priority(_pick(cells, colmap, PRIORITY_COLS)),
            layers_cell=layers_cell,
            layers_from_named_col=layers_named,
            status="removed" if in_removed else "active",
            cells=tuple(cells),
            lineno=lineno,
            basis_cell=basis_cell,
            basis_from_named_col=basis_named,
        ))
    return rows


def read_active_fr_rows(content: str, *, rejects: list | None = None) -> list[FrTableRow]:
    """``read_fr_rows`` filtered to live requirements."""
    return [row for row in read_fr_rows(content, rejects=rejects) if not row.removed]


__all__ = [
    "BASIS_COLS",
    "DEFAULT_PRIORITY",
    "FrTableRow",
    "LAYERS_COLS",
    "NAME_COLS",
    "PRIORITIES",
    "PRIORITY_COLS",
    "TITLE_COLS",
    "normalise_priority",
    "read_active_fr_rows",
    "read_fr_rows",
    "split_cells",
]

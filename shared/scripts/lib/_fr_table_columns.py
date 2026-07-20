"""Column semantics for the FR-table reader: which cell means what.

The third layer of the reader's split, and the seam is a clean one:

* ``_fr_table_cells`` — a row of markdown text becomes a list of cells.
* ``_fr_table_columns`` (here) — a header row becomes a column map, and a cell
  list plus that map becomes a named field.
* ``fr_table_reader`` — the document state machine: headings, removal sections,
  fold-map spans, and which rows are requirements at all.

Nothing here knows about requirements, headings or documents; it only answers
"given this header, which index holds the title / the priority / the layers".
That makes the header-recognition rule — the one FV-4 got wrong — a single
testable function rather than a branch buried in a loop.
"""

from __future__ import annotations

import re

#: Column-name synonyms for the requirement's semantic body, first match wins.
TITLE_COLS: tuple[str, ...] = ("description", "name", "text", "requirement", "title")
NAME_COLS: tuple[str, ...] = ("name",)
PRIORITY_COLS: tuple[str, ...] = ("priority",)
LAYERS_COLS: tuple[str, ...] = ("layers", "layer")

#: The closed priority vocabulary and the coercion target.
PRIORITIES: tuple[str, ...] = ("Must", "Should", "May")
DEFAULT_PRIORITY = "Must"
_PRIORITY_BY_LOWER = {p.lower(): p for p in PRIORITIES}

#: A ``|---|:--:|`` alignment cell, or an empty one.
_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$|^$")


def normalise_priority(value: str) -> str:
    """Map a priority cell onto the closed vocabulary.

    An unrecognised value is coerced rather than dropping its row. ``Must`` is
    the safe coercion in both directions that matter: Group D maps it to the
    highest severity and the RTM files it under the must-requirements, so a
    typo makes the audit LOUDER, never blinder.
    """
    return _PRIORITY_BY_LOWER.get(value.strip().lower(), DEFAULT_PRIORITY)


def header_map(cells: list[str]) -> dict[str, int] | None:
    """Return a column-name → index map when ``cells`` is a usable header row.

    A header is recognised by naming a Priority column — the one column every
    one of the five historical shapes carries. Deliberately NOT by
    ``cells[0] == "id"``: that was FV-4, which made Group I audit nothing at all
    on the traceability-fixture shape whose id column is headed ``FR``.

    Returning ``None`` means "this table row is not a requirements header", and
    the reader treats that as having LEFT the requirements table rather than as
    a row to ignore — see its ``read_fr_rows`` docstring.
    """
    low = [c.lower() for c in cells]
    if not any(name in low for name in PRIORITY_COLS):
        return None
    return {name: i for i, name in enumerate(low)}


def is_separator_row(cells: list[str]) -> bool:
    """True for a ``|---|:--:|`` alignment row (and an all-empty row).

    Load-bearing: a separator sits directly under every header, and a reader
    that treated it as "a table row naming no Priority column" would invalidate
    the map it had just built and drop the entire table.
    """
    return all(_SEPARATOR_CELL_RE.match(cell) for cell in cells)


def pick(cells: list[str], colmap: dict[str, int], names: tuple[str, ...]) -> str:
    """The first of ``names`` the header maps, or ``""``.

    No positional fallback: if the header does not name the column, we do not
    have it. Guessing is what produced FV-3.
    """
    for name in names:
        idx = colmap.get(name)
        if idx is not None and idx < len(cells):
            return cells[idx]
    return ""


def layers_cell(cells: list[str], colmap: dict[str, int]) -> tuple[str, bool]:
    """``(raw Layers cell, came_from_a_named_column)``.

    Read ONLY when the header names it, so the adopt 5-column Description cell
    is never mistaken for a layer declaration. The flag is what keeps a guess
    from being recorded as an author's explicit provenance.
    """
    if any(name in colmap for name in LAYERS_COLS):
        return pick(cells, colmap, LAYERS_COLS), True
    return "", False


__all__ = [
    "DEFAULT_PRIORITY",
    "LAYERS_COLS",
    "NAME_COLS",
    "PRIORITIES",
    "PRIORITY_COLS",
    "TITLE_COLS",
    "header_map",
    "is_separator_row",
    "layers_cell",
    "normalise_priority",
    "pick",
]

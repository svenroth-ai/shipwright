"""The ONE FR-table shape both producers emit — header, Area, and the Layers marker.

Campaign "Requirements Catalog", sub-iterate S5. S4 collapsed five *parsers* into
one header-driven reader; the *producers* still disagreed, so the divergence had
simply moved upstream. This module is the producer-side counterpart:
``fr_table_reader`` is how the shape is read, this is what the shape IS.

    | ID | Area | Name | Priority | Description | Basis | Layers |

**It is deliberately a two-sided contract, not a writer helper.** The
``(inferred)`` marker lives here and the compliance-side provenance rule imports
it from here, because producer and consumer of a serialized format that each keep
their own copy of its grammar is the exact defect class this campaign exists to
close (ADR-024). One definition, both directions.

The marker matters more than it looks. A probe run while writing this module
found that ``unit(inferred)`` — the same tokens, one space short — parses to
**zero** required layers, because ``_parse_layers`` splits on ``[,\\s/|]+`` and
``unit(inferred)`` is then a single token that is not a layer name. The
requirement keeps advisory provenance and silently loses its coverage
requirement. So the separator is load-bearing and no caller should be hand-
formatting this cell; ``render_layers`` is the only sanctioned way to write one.

Decision D7 (``Area`` is rendered from the group digit, never stored) is
implemented here too. A stored ``Area`` would be a SECOND grouping axis beside the
id's group digit, and two axes for one fact diverge — that is not hypothetical,
it is adopt's current bug, where the folder decides the number and nothing keeps
the two in step. A computed label cannot drift from its key.

Pure: no I/O, no globals.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# The canonical header
# ---------------------------------------------------------------------------

#: Column order, authoritative. ``Basis`` replaces ``Source`` (D3: a file path is
#: implementation detail and answers "where we looked", not "how we know").
FR_TABLE_COLUMNS: tuple[str, ...] = (
    "ID", "Area", "Name", "Priority", "Description", "Basis", "Layers",
)

#: The exact header line every producer emits, and the separator beneath it.
#: A constant rather than a convention: "byte-compatible headers" is otherwise
#: only checkable by eye, and a one-column-name drift between the adopt writer
#: and the greenfield template looks correct in both files independently.
FR_TABLE_HEADER = "| " + " | ".join(FR_TABLE_COLUMNS) + " |"
FR_TABLE_SEPARATOR = "|" + "|".join("---" for _ in FR_TABLE_COLUMNS) + "|"


# ---------------------------------------------------------------------------
# Layers — the (inferred) marker contract
# ---------------------------------------------------------------------------

#: The literal marker meaning "these layers were DERIVED, not declared".
#: Machine-emitted cells carry it; a human declaration does not, and reads as
#: `explicit` provenance. Keeping the marker narrow is the point — a cell
#: reading `unit, e2e (auto)` must NOT be silently downgraded out of the hard
#: gate, so only this exact word counts.
INFERRED_MARKER = "(inferred)"

#: Matched narrowly and case-insensitively: ``\(\s*inferred\s*\)``.
INFERRED_MARKER_RE = re.compile(r"\(\s*inferred\s*\)", re.IGNORECASE)


def has_inferred_marker(cell: str) -> bool:
    """True when ``cell`` carries the literal ``(inferred)`` marker."""
    return bool(INFERRED_MARKER_RE.search(cell))


def render_layers(layers, *, inferred: bool) -> str:
    """Serialize required layers into a ``Layers`` cell.

    The ONLY sanctioned way to write this cell. Layers are comma-separated and
    the marker is separated by a space, because the reader tokenises on
    ``[,\\s/|]+`` and a marker glued to the last layer swallows it — see the
    module docstring. An empty ``layers`` with ``inferred=True`` yields the bare
    marker, which reads as advisory-with-no-required-layers rather than as an
    empty cell that would be re-inferred from the title.
    """
    body = ", ".join(layers)
    if not inferred:
        return body
    return f"{body} {INFERRED_MARKER}" if body else INFERRED_MARKER


# ---------------------------------------------------------------------------
# Area — rendered from the group digit (D7)
# ---------------------------------------------------------------------------

#: A canonical group digit pair, as it appears in ``FR-XX.YY``. The same tier
#: ``fr_table_reader`` admits rows at (its rule 1) and the same one manifest
#: schema v3 derives a namespace from — a looser tier here would re-open the
#: divergence S4 closed.
_ID_GROUP_RE = re.compile(r"^FR-(\d{2})\.\d{2}$")

#: A split directory: two leading digits, a separator, then the human name.
_SPLIT_RE = re.compile(r"^(\d{2})[-_](.+)$")


def group_of(fr_id: str) -> str | None:
    """The two-digit group of a canonical FR id, or ``None`` if it has none."""
    match = _ID_GROUP_RE.match(fr_id.strip())
    return match.group(1) if match else None


def split_group(split_dir_name: str) -> str | None:
    """The group a split directory declares (``01-adopted`` → ``01``)."""
    match = _SPLIT_RE.match(split_dir_name.strip())
    return match.group(1) if match else None


def label_of_split(split_dir_name: str) -> str:
    """The human label a split carries (``01-adopted`` → ``Adopted``).

    Word-per-word title casing, so ``03-payments-api`` reads ``Payments Api``.
    Deliberately no acronym table: a curated list of "words to shout" is a second
    source of truth about names, and rendering ``Api`` slightly plainly is
    cheaper than maintaining one. An author who wants ``API`` renames the split.
    """
    match = _SPLIT_RE.match(split_dir_name.strip())
    raw = match.group(2) if match else split_dir_name.strip()
    words = [w for w in re.split(r"[-_\s]+", raw) if w]
    return " ".join(w[:1].upper() + w[1:] for w in words) if words else ""


def area_for(fr_id: str, split_dir_name: str) -> str:
    """The ``Area`` cell for ``fr_id`` as filed under ``split_dir_name``.

    The split supplies the label only when it actually declares the id's own
    group. When they disagree — a requirement filed under the wrong split — the
    **id is authoritative** (D7) and the cell falls back to ``Group NN``. That
    fallback is deliberately plain: it reads as unnamed rather than as a claim,
    and it puts the inconsistency in the rendered table where someone will see
    it, instead of letting the folder quietly rename the requirement's group.
    """
    group = group_of(fr_id)
    if group is None:
        return label_of_split(split_dir_name)
    if split_group(split_dir_name) == group:
        return label_of_split(split_dir_name)
    return f"Group {group}"


__all__ = [
    "FR_TABLE_COLUMNS",
    "FR_TABLE_HEADER",
    "FR_TABLE_SEPARATOR",
    "INFERRED_MARKER",
    "INFERRED_MARKER_RE",
    "area_for",
    "group_of",
    "has_inferred_marker",
    "label_of_split",
    "render_layers",
    "split_group",
]

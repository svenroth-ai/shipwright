"""The row type the FR-table reader produces: the contract between its layers.

Fourth module of the reader's split, and the seam is the one the other three
already implied:

* ``_fr_table_cells`` — markdown text becomes a list of cells.
* ``_fr_table_columns`` — a header row becomes a column map; a cell list plus
  that map becomes a named field.
* ``_fr_table_row`` (here) — the shape those named fields are assembled into.
* ``fr_table_reader`` — the document state machine that does the assembling.

Extracted in campaign S5 when the reader needed two additive fields and stood at
exactly its 300-line budget. The alternative — ratcheting the budget — would have
bought the same two fields by spending the invariant that keeps the reader
readable, which is the wrong trade for a dataclass that was never state-machine
code in the first place. Re-exported from ``fr_table_reader`` so every existing
``from fr_table_reader import FrTableRow`` keeps working.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FrTableRow:
    """One FR row, with every cell each of the five consumers needs kept apart.

    The consumers deliberately want DIFFERENT projections of the same row —
    traceability wants one semantic body, Group I's naming fence needs Name and
    Description kept separate, and the layers provenance rules need to know
    whether the Layers cell came from a NAMED column or from a positional guess.
    Collapsing those here would just move the divergence downstream.
    """

    id: str
    #: The Name column, or ``""`` when the table has no Name column.
    name: str
    #: The requirement's semantic body (Description / Requirement / Text / …).
    text: str
    priority: str
    #: Raw Layers cell — unparsed, because layer semantics are the caller's.
    layers_cell: str
    #: True when the governing header actually NAMED a Layers column — the
    #: difference between an author's declaration and a column that is absent.
    layers_from_named_col: bool
    #: ``"active"`` or ``"removed"`` (a ``## Removed Requirements`` section).
    status: str
    #: Every cell of the row, escape-resolved, for consumers needing more.
    cells: tuple[str, ...]
    #: 0-based line number in the source text.
    lineno: int
    #: Raw ``Basis`` cell (campaign S5) — the closed provenance vocabulary of
    #: SPEC §3.2. Unvalidated here: ``fr_basis`` owns the vocabulary, exactly as
    #: ``requirement_model`` owns layer semantics for ``layers_cell``.
    basis_cell: str = ""
    #: True when the governing header NAMED a Basis column. Read only from a
    #: column literally headed ``Basis``: a legacy ``Source`` cell holds a file
    #: path and never claimed to be a basis, so scoring it against the
    #: vocabulary would fail every already-adopted repo on its own history.
    basis_from_named_col: bool = False

    @property
    def removed(self) -> bool:
        return self.status == "removed"


__all__ = ["FrTableRow"]

"""Surgically rewrite ONE active FR row's ``Layers`` cell in an existing ``spec.md``.

Every other writer in this family (``fr_table_shape.render_layers``,
``spec_table.render_fr_table``) EMITS a fresh table; nothing rewrites a single
cell of an already-authored, hand-maintained document in place. This is that
missing counterpart, needed because promotion (P3.5) edits one cell of a live
FR table rather than regenerating it — regenerating would blow away every
hand edit a maintainer made to the surrounding rows.

**Deliberately requires the canonical column order** (``fr_table_shape.
FR_TABLE_COLUMNS``) to be exactly what the table's header line declares —
refuses (raises) rather than guessing a column index from a re-ordered or
non-canonical header. ``fr_table_reader`` tolerates re-ordered/renamed
columns because it only ever READS; a WRITER that guessed wrong would corrupt
a cell silently, which is a materially worse failure than refusing to write
at all.

The escaping half is a deliberate, pinned MIRROR of
``shared/scripts/markdown_table.escape_cell`` (not an import): that module
lives one directory above ``shared/scripts/lib/``, and reaching across that
boundary from a ``lib/`` module has no existing precedent in this codebase
(``_fr_table_cells.split_cells`` made the same choice, mirroring rather than
importing, for the same reason). ``test_escape_cell_mirrors_markdown_table``
pins the two against drift.
"""

from __future__ import annotations

import re
from pathlib import Path

try:  # Package context (shared/tests: `shared/scripts` on sys.path).
    from .atomic_write import durable_atomic_write
    from .fr_table_reader import read_fr_rows
    from .fr_table_shape import (
        FR_TABLE_COLUMNS,
        FR_TABLE_HEADER,
        INFERRED_MARKER_RE,
        has_inferred_marker,
    )
    from .requirement_model import LAYERS
except ImportError:  # Loaded by file path.
    from atomic_write import durable_atomic_write  # type: ignore
    from fr_table_reader import read_fr_rows  # type: ignore
    from fr_table_shape import (  # type: ignore
        FR_TABLE_COLUMNS,
        FR_TABLE_HEADER,
        INFERRED_MARKER_RE,
        has_inferred_marker,
    )
    from requirement_model import LAYERS  # type: ignore

#: Tokeniser mirrored from ``_requirement_parse._parse_layers`` (compliance
#: plugin — not imported: ``lib/`` cannot reach across the plugin boundary,
#: ADR-045). Splitting the SAME way is what makes :func:`live_declared_layers`
#: agree with what a fresh manifest re-collection would compute for this cell.
_LAYER_TOKEN_RE = re.compile(r"[,\s/|]+")

#: Mirrors ``markdown_table._TABLE_CELL_TRANSFORMS`` exactly — same order
#: (backslash first), same substitutions. See module docstring.
_CELL_TRANSFORMS: tuple[tuple[str, str], ...] = (
    ("\\", "\\\\"),
    ("|", "\\|"),
    ("\r\n", " "),
    ("\r", " "),
    ("\n", " "),
)


def _escape_cell(value: str) -> str:
    text = value
    for src, dst in _CELL_TRANSFORMS:
        text = text.replace(src, dst)
    return text


class LayerCellWriteError(ValueError):
    """The row/header this call needs is not in the shape this writer trusts."""


def _line_ending(line: str) -> tuple[str, str]:
    for eol in ("\r\n", "\n", "\r"):
        if line.endswith(eol):
            return line[: -len(eol)], eol
    return line, ""


def _canonical_layers_index(content: str) -> tuple[int, int]:
    """The canonical header's own 0-based line number, and the 0-based index
    of its ``Layers`` column — requiring EXACTLY one line in ``content`` to
    equal :data:`FR_TABLE_HEADER` verbatim (trailing whitespace aside).
    Raises on zero or more-than-one such line — a writer must never guess
    between two candidate headers.

    The line number is returned so a caller can also confirm the ROW it is
    about to edit is actually governed by THIS header, not merely that this
    header exists somewhere in the document: a canonical id living only
    under a second, differently-shaped priority-bearing table would
    otherwise get a hardcoded column index applied to a row that header
    never declared."""
    matches = [
        lineno for lineno, line in enumerate(content.splitlines())
        if line.rstrip() == FR_TABLE_HEADER
    ]
    if not matches:
        raise LayerCellWriteError(
            "no line in this spec matches the canonical FR-table header "
            f"{FR_TABLE_HEADER!r} — refusing to guess a column layout"
        )
    if len(matches) > 1:
        raise LayerCellWriteError(
            f"{len(matches)} lines match the canonical FR-table header — "
            "refusing to guess which one governs the target row"
        )
    return matches[0], FR_TABLE_COLUMNS.index("Layers")


def write_layers_cell(content: str, fr_id: str, new_cell_text: str) -> str:
    """Return ``content`` with ``fr_id``'s ACTIVE row's Layers cell replaced.

    Idempotent: if the row's current Layers cell already equals
    ``new_cell_text``, ``content`` is returned byte-identical (a repeat call —
    the automated tool re-running over an already-promoted FR — is a safe
    no-op, not a second write). Every OTHER LINE, including the target row's
    own line ending, is preserved untouched.

    **Value-preserving, not byte-preserving, for the target row's OTHER
    cells** (Low finding, Stage-3 doubt-review round 3, P3.5 post-push
    round, accepted-not-fixed): the row is re-rendered whole via
    :func:`_escape_cell`, so a promotion can cosmetically re-escape a
    sibling cell (a hand-written single backslash like ``C:\\repo\\spec``
    becomes the doubled, escaped ``C:\\\\repo\\\\spec`` on disk) or collapse a
    sibling cell's hand-added column-alignment padding to a single space —
    never changes what a re-read of the row MEANS (``_escape_cell``/
    ``split_cells`` are exact inverses), only its literal bytes. Left as a
    pinned, tested contract rather than fixed: latent in this repo today
    (no live FR row contains a backslash or non-canonical padding),
    convergent (idempotent from the second write), and a byte-preserving
    splice would require threading raw per-cell byte spans through the
    shared ``fr_table_reader``/``_fr_table_cells`` reader used well beyond
    this one writer — a materially larger, riskier change than the gap it
    closes. See ``test_normalizes_a_hand_written_backslash_in_an_untouched_
    cell_when_the_row_is_rewritten`` and its column-padding sibling.

    Raises :class:`LayerCellWriteError` when: the table header is not exactly
    the canonical shape (see :func:`_canonical_layers_index`); no ACTIVE row
    named ``fr_id`` exists; more than one ACTIVE row shares ``fr_id`` (a
    document-level id collision — writing the first match is exactly the
    ambiguity the collision escalation exists to flag, so a writer must
    refuse rather than guess); the target row sits ABOVE the canonical
    header; the target row's cell count does not match the canonical
    header's own column count; or the row's OWN governing header (as the
    general reader resolved it) does not actually place Layers at the
    canonical index (a canonical id living only under a second, SAME-WIDTH,
    differently-ordered priority-bearing table would pass the first two
    checks and still get the wrong cell silently overwritten).
    """
    rows = read_fr_rows(content)
    matches = [row for row in rows if row.id == fr_id and not row.removed]
    if not matches:
        raise LayerCellWriteError(f"no ACTIVE FR row {fr_id!r} found in this spec")
    if len(matches) > 1:
        raise LayerCellWriteError(
            f"{len(matches)} ACTIVE FR rows share id {fr_id!r} in this spec — "
            "refusing to guess which one this write targets"
        )
    target = matches[0]
    if target.layers_cell == new_cell_text:
        return content

    header_lineno, layers_idx = _canonical_layers_index(content)
    if target.lineno <= header_lineno:
        raise LayerCellWriteError(
            f"row for {fr_id!r} (line {target.lineno + 1}) is not below the "
            f"canonical FR-table header (line {header_lineno + 1}) — refusing "
            "to guess it is governed by a header it precedes"
        )
    cells = list(target.cells)
    if len(cells) != len(FR_TABLE_COLUMNS):
        raise LayerCellWriteError(
            f"row for {fr_id!r} (line {target.lineno + 1}) has {len(cells)} "
            f"cell(s), not the {len(FR_TABLE_COLUMNS)} the canonical header "
            "declares — refusing to guess it is governed by that header "
            "rather than a second, differently-shaped table"
        )
    # A second, SAME-WIDTH, differently-ORDERED table passes both checks
    # above. `target.layers_cell` was resolved via the row's OWN colmap —
    # comparing it to the canonical hardcoded index catches a mismatch
    # (not perfect: a coincidental content match would slip through).
    if not target.layers_from_named_col or cells[layers_idx] != target.layers_cell:
        raise LayerCellWriteError(
            f"row for {fr_id!r} (line {target.lineno + 1}) is not actually "
            "governed by the canonical header's own column layout (its "
            "Layers cell does not live at the canonical index) — refusing "
            "to guess it is governed by that header rather than a second, "
            "same-width, differently-ordered table"
        )
    lines = content.splitlines(keepends=True)
    body, ending = _line_ending(lines[target.lineno])
    cells[layers_idx] = new_cell_text
    new_line = "| " + " | ".join(_escape_cell(c) for c in cells) + " |" + ending
    lines[target.lineno] = new_line
    return "".join(lines)


def resolve_spec_path_within_root(project_root, rel_path: str) -> Path:
    """``project_root / rel_path``, refusing to resolve OUTSIDE ``project_root``.

    Both promotion tools (automated and operator) get ``rel_path`` from a
    manifest node's ``spec_path`` — a field this codebase treats as trusted
    everywhere else it is consumed, but neither tool AUTHORS that field
    itself, and a two-line guard against a manifest reporting a path that
    escapes the project (a corrupt or hand-edited manifest) costs nothing.
    """
    full_path = (Path(project_root) / rel_path).resolve()
    root = Path(project_root).resolve()
    try:
        full_path.relative_to(root)
    except ValueError:
        raise LayerCellWriteError(
            f"manifest spec_path {rel_path!r} resolves outside {root} — refusing to use it"
        ) from None
    return full_path


def is_layers_cell_explicit_live(content: str, fr_id: str) -> bool:
    """Whether ``fr_id``'s ACTIVE row's Layers cell is CURRENTLY explicit —
    read straight from ``content``, never from a possibly-stale collector
    field.

    The committed ``test-traceability.json`` is a derived, un-committed-per-
    iterate snapshot (``derived_snapshots.DERIVED_SNAPSHOTS``) that this
    promotion tool never regenerates, so its ``required_layers_source`` can
    lag one promotion behind whatever this run has already written to
    ``spec.md`` — exactly the staleness ``_layer_coverage_core``'s own
    enforcement gates refuse to trust ("the committed test-traceability.json
    is never the enforcement source", R3). Re-deriving THIS one fact from the
    live document each time is what makes a same-session re-run over an
    already-promoted FR see it as already explicit rather than as a
    contradiction (``layer_promotion.evaluate_fr``'s ledger-drift branch).

    A non-empty cell with no ``(inferred)`` marker is "explicit" — the same
    two-part rule ``_requirement_parse.parse_requirements`` uses for its
    ``explicit`` provenance branches (an empty cell can never be explicit; a
    marked cell never is, however it parses). Returns ``False`` — never
    raises — when ``fr_id`` has no active row at all: a structurally missing
    row is conservatively "not yet promoted", and a caller that goes on to
    attempt a promotion for it hits :func:`write_layers_cell`'s own
    "no ACTIVE FR row" error instead.
    """
    return live_required_layers(content, fr_id) is not None


def live_required_layers(content: str, fr_id: str) -> list[str] | None:
    """The ACTUAL layer names in ``fr_id``'s ACTIVE row's Layers cell, parsed
    fresh from ``content`` — or ``None`` when the row is missing, or the cell
    is empty/still carries the ``(inferred)`` marker (not explicit yet).

    Stronger than a fingerprint comparison for detecting a hand narrowing: a
    ledger entry's ``required_layers`` is compared against what this reads,
    not against a hash, so a maintainer manually shrinking an explicit cell
    (``unit, integration`` → ``unit``) is caught even though nothing about
    the FR's *evidence* fingerprint changed at all.

    Deliberately comma-only splitting, NOT :data:`_LAYER_TOKEN_RE` — this
    answers "is this explicit", narrower than :func:`live_declared_layers`'s
    "what does this cell declare"; a caller comparing this against a
    differently-tokenised set (``layer_promotion._narrowed_since_promotion``)
    must canonicalise both sides itself.
    """
    rows = read_fr_rows(content)
    row = next((r for r in rows if r.id == fr_id and not r.removed), None)
    if row is None:
        return None
    cell = row.layers_cell.strip()
    if not cell or has_inferred_marker(cell):
        return None
    return [tok.strip() for tok in cell.split(",") if tok.strip()]


def live_declared_layers(content: str, fr_id: str) -> list[str] | None:
    """The canonical layer names ``fr_id``'s ACTIVE row's Layers cell
    CURRENTLY declares, regardless of the ``(inferred)`` marker — unlike
    :func:`live_required_layers`, which returns ``None`` for an inferred
    cell because IT answers "is this explicit". ``None`` only when the row
    is missing entirely; an empty/all-unrecognised cell returns ``[]``.

    A promotion's ``required_before`` once trusted the possibly-stale
    manifest's own ``required_layers`` alone — an inferred cell reading
    ``unit, e2e (inferred)`` against a manifest still saying ``["unit"]``
    (ordinary snapshot staleness) silently DROPPED the hand-declared
    ``e2e`` on rewrite. This reads the same way a fresh manifest
    re-collection would (mirrors ``_requirement_parse._parse_layers``,
    kept an independent copy — ADR-045), so a caller can union it in
    rather than trust the manifest's value alone.
    """
    rows = read_fr_rows(content)
    row = next((r for r in rows if r.id == fr_id and not r.removed), None)
    if row is None:
        return None
    out: list[str] = []
    for tok in _LAYER_TOKEN_RE.split(row.layers_cell.strip()):
        low = tok.lower()
        if low in LAYERS and low not in out:
            out.append(low)
    return out


def live_cell_has_non_canonical_content(content: str, fr_id: str) -> bool:
    """Whether ``fr_id``'s ACTIVE row's Layers cell CURRENTLY carries any
    text beyond the canonical layer tokens and the ``(inferred)`` marker —
    a hand-added annotation (``unit (inferred) - integration deferred, see
    ADR-031``) or a non-canonical token (``unit, db (inferred)``).

    "Widen, never narrow" — this mechanism's own repeated invariant (see
    :func:`live_declared_layers`) — holds over the canonical layer SET a
    promotion computes, not over the cell's raw TEXT: ``render_layers``
    regenerates the WHOLE cell from that set alone, so any residual text a
    maintainer added is silently deleted on promotion, with no warning and
    no escalation, unless a caller checks first (Stage-3 doubt-review round
    2, P3.5 post-push round — the one axis the stale-manifest-narrowing fix
    above does not reach). Latent in this repo today (every live cell is
    pure-canonical); live for the first hand-annotated cell here, or for
    any adopter.

    ``False`` when the row is missing entirely — nothing to compare, and a
    caller that goes on to write anyway hits :func:`write_layers_cell`'s
    own "no ACTIVE FR row" error instead.
    """
    rows = read_fr_rows(content)
    row = next((r for r in rows if r.id == fr_id and not r.removed), None)
    if row is None:
        return False
    residual = INFERRED_MARKER_RE.sub("", row.layers_cell)
    return any(
        tok.strip().lower() not in LAYERS
        for tok in _LAYER_TOKEN_RE.split(residual)
        if tok.strip()
    )


def atomic_write_text(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` durably and atomically: a
    hand-maintained ``spec.md`` — the document ``write_layers_cell``'s own
    docstring calls out as worst to corrupt — deserves the same
    interrupted-write safety ``layer_promotion_ledger.write_ledger`` already
    gives its own file. Delegates to the shared
    ``atomic_write.durable_atomic_write`` primitive rather than a locally
    duplicated fixed-name tmp file: two concurrent writers to the same
    target collided on that fixed name, and one's cleanup could delete the
    other's in-flight tmp file between its write and its replace."""
    durable_atomic_write(Path(path), content)


__all__ = [
    "LayerCellWriteError", "write_layers_cell", "is_layers_cell_explicit_live",
    "live_required_layers", "live_declared_layers", "live_cell_has_non_canonical_content",
    "atomic_write_text", "resolve_spec_path_within_root",
]

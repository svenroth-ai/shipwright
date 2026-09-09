"""Pins ``lib.fr_layer_cell_writer.write_layers_cell``'s surgical-edit contract."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pytest

from lib.fr_layer_cell_writer import (
    LayerCellWriteError,
    live_cell_has_non_canonical_content,
    live_declared_layers,
    resolve_spec_path_within_root,
    write_layers_cell,
)
from lib.fr_table_reader import read_fr_rows
from lib.fr_table_shape import FR_TABLE_HEADER, FR_TABLE_SEPARATOR
from markdown_table import escape_cell  # only tests may cross-import both sides of a mirror


# Mirrors the ACTUAL shape of .shipwright/planning/01-adopted/spec.md: exactly
# ONE header/separator pair for the whole document. A "Removed Requirements"
# heading does not repeat the header (fr_table_reader rule 3: the column map
# SURVIVES a heading) -- this repo's own spec never emits a second one either.
_DOC = "\n".join([
    "# Spec",
    "",
    "## Functional Requirements",
    "",
    FR_TABLE_HEADER,
    FR_TABLE_SEPARATOR,
    "| FR-01.01 | Adopted | /shipwright-run | Must | Does a thing. | code | unit (inferred) |",
    "| FR-01.02 | Adopted | /shipwright-project | Must | Does another. | code | unit (inferred) |",
    "",
    "## Removed Requirements",
    "",
    "| FR-01.99 | Adopted | Old thing | Must | Gone. | code | unit (inferred) |",
    "",
])


def test_promotes_the_named_row_only():
    out = write_layers_cell(_DOC, "FR-01.01", "unit")
    lines = out.splitlines()
    assert lines[6] == "| FR-01.01 | Adopted | /shipwright-run | Must | Does a thing. | code | unit |"
    # The sibling row is byte-identical.
    assert lines[7] == _DOC.splitlines()[7]


def test_is_idempotent_on_a_repeat_call():
    once = write_layers_cell(_DOC, "FR-01.01", "unit, integration")
    twice = write_layers_cell(once, "FR-01.01", "unit, integration")
    assert once == twice


def test_returns_input_unchanged_when_cell_already_matches():
    out = write_layers_cell(_DOC, "FR-01.01", "unit (inferred)")
    assert out == _DOC


def test_never_touches_a_removed_row():
    with pytest.raises(LayerCellWriteError, match="ACTIVE"):
        write_layers_cell(_DOC, "FR-01.99", "unit")


def test_unknown_fr_id_raises():
    with pytest.raises(LayerCellWriteError, match="FR-99.99"):
        write_layers_cell(_DOC, "FR-99.99", "unit")


def test_two_active_rows_sharing_an_id_refuses_to_guess():
    # external code review (glm/medium, P3.5 round 1): a document-level id
    # collision must never be resolved by writing the first match.
    doc = _DOC.replace(
        "| FR-01.02 | Adopted | /shipwright-project | Must | Does another. | code | unit (inferred) |",
        "| FR-01.01 | Adopted | /shipwright-project | Must | Does another. | code | unit (inferred) |",
    )
    with pytest.raises(LayerCellWriteError, match="2 ACTIVE FR rows share"):
        write_layers_cell(doc, "FR-01.01", "unit")


def test_non_canonical_header_refuses_to_write():
    doc = _DOC.replace(FR_TABLE_HEADER, "| ID | Name | Priority | Description | Layers |")
    with pytest.raises(LayerCellWriteError, match="canonical"):
        write_layers_cell(doc, "FR-01.01", "unit")


def test_two_canonical_headers_refuses_to_guess():
    two_header_doc = "\n".join(_DOC.splitlines()[:8] + [FR_TABLE_HEADER, FR_TABLE_SEPARATOR]
                                + _DOC.splitlines()[8:])
    with pytest.raises(LayerCellWriteError, match="2 lines match"):
        write_layers_cell(two_header_doc, "FR-01.01", "unit")


def test_id_only_under_a_foreign_priority_bearing_table_refuses_to_guess():
    """One canonical FR table (governing FR-01.01/FR-01.02, untouched by this
    call) plus one foreign, differently-shaped priority-bearing table whose
    only row shares an id with a REAL requirement elsewhere (external code
    review, medium, P3.5 post-push round): the document has exactly one
    canonical header, so the round-1 "2 lines match" guard alone would let
    this through and apply the canonical Layers index to a row that header
    never declared."""
    doc = "\n".join(_DOC.splitlines() + [
        "",
        "## A one-off compliance table",
        "",
        "| ID | Priority | Layers |",
        "|---|---|---|",
        "| FR-09.01 | Must | integration |",
    ])
    with pytest.raises(LayerCellWriteError, match="cell\\(s\\), not the"):
        write_layers_cell(doc, "FR-09.01", "unit")


def test_id_under_a_same_width_reordered_foreign_table_refuses_to_guess():
    """Stage-3 doubt-review Medium finding, P3.5 post-push round: a foreign
    table with the SAME column COUNT as canonical (7) but Layers/Basis
    swapped (Layers at index 5, not the canonical 6) passes both the
    line-below-header and cell-count checks — only comparing the row's OWN
    resolved Layers cell against the canonical hardcoded index catches it."""
    doc = "\n".join(_DOC.splitlines() + [
        "",
        "## A same-width, reordered compliance table",
        "",
        "| ID | Area | Name | Priority | Description | Layers | Basis |",
        "|---|---|---|---|---|---|---|",
        "| FR-09.01 | x | y | Must | z | e2e | code |",
    ])
    with pytest.raises(LayerCellWriteError, match="does not live at the canonical index"):
        write_layers_cell(doc, "FR-09.01", "unit")


def test_preserves_crlf_line_ending_on_the_edited_line_only():
    doc = _DOC.replace(
        "| FR-01.01 | Adopted | /shipwright-run | Must | Does a thing. | code | unit (inferred) |\n",
        "| FR-01.01 | Adopted | /shipwright-run | Must | Does a thing. | code | unit (inferred) |\r\n",
    )
    out = write_layers_cell(doc, "FR-01.01", "unit")
    assert "| FR-01.01 | Adopted | /shipwright-run | Must | Does a thing. | code | unit |\r\n" in out
    # An untouched line elsewhere keeps its own (LF) ending, not CRLF.
    unit02_line = next(ln for ln in out.split("\n") if ln.startswith("| FR-01.02"))
    assert not unit02_line.endswith("\r")


def test_escapes_a_pipe_in_an_untouched_cell_when_the_row_is_rewritten():
    doc = _DOC.replace(
        "| FR-01.01 | Adopted | /shipwright-run | Must | Does a thing. | code | unit (inferred) |",
        "| FR-01.01 | Adopted | /shipwright-run | Must | Does a\\|thing. | code | unit (inferred) |",
    )
    out = write_layers_cell(doc, "FR-01.01", "unit")
    assert "Does a\\|thing." in out


def test_normalizes_a_hand_written_backslash_in_an_untouched_cell_when_the_row_is_rewritten():
    # Low finding, Stage-3 doubt-review round 3, P3.5 post-push round:
    # write_layers_cell rewrites the WHOLE row line, not just the Layers
    # cell -- a promotion re-escapes every OTHER cell too. Value-preserving
    # (round-trips back to the same content on the next read, since
    # `_escape_cell`/`split_cells` are exact inverses -- see this module's
    # docstring) but NOT byte-preserving: a hand-written single backslash
    # (`C:\repo\spec`, content per `split_cells`'s own contract) becomes a
    # doubled, escaped backslash (`C:\\repo\\spec`) on disk once ANY cell
    # in that row is rewritten. Rebuttal (ADR "Stage-3 doubt-review findings,
    # round 3"): accepted as a pinned, tested contract rather than fixed --
    # latent in this repo today (no live FR row contains a backslash),
    # convergent (idempotent from the second write), and closing it would
    # require threading raw per-cell byte spans through the shared
    # `fr_table_reader`/`_fr_table_cells` reader, a materially larger and
    # riskier change than the gap it closes.
    doc = _DOC.replace(
        "| FR-01.01 | Adopted | /shipwright-run | Must | Does a thing. | code | unit (inferred) |",
        "| FR-01.01 | Adopted | C:\\repo\\spec | Must | Does a thing. | code | unit (inferred) |",
    )
    out = write_layers_cell(doc, "FR-01.01", "unit")
    assert "C:\\\\repo\\\\spec" in out
    # Semantically lossless: reading the rewritten row back yields the
    # SAME value the hand-written cell originally meant.
    assert read_fr_rows(out)[0].cells[2] == "C:\\repo\\spec"


def test_collapses_hand_added_column_alignment_padding_in_an_untouched_cell_when_the_row_is_rewritten():
    # Sibling case to the backslash one above, same rebuttal: `split_cells`
    # strips each cell, so hand-added alignment padding around an UNTOUCHED
    # cell is lost once the row is rewritten for an unrelated cell's edit.
    doc = _DOC.replace(
        "| FR-01.01 | Adopted | /shipwright-run | Must | Does a thing. | code | unit (inferred) |",
        "| FR-01.01 | Adopted |   /shipwright-run   | Must | Does a thing. | code | unit (inferred) |",
    )
    out = write_layers_cell(doc, "FR-01.01", "unit")
    assert "|   /shipwright-run   |" not in out
    assert "| /shipwright-run |" in out


def test_resolve_spec_path_within_root_accepts_a_normal_relative_path(tmp_path):
    (tmp_path / ".shipwright" / "planning" / "01-adopted").mkdir(parents=True)
    resolved = resolve_spec_path_within_root(
        tmp_path, ".shipwright/planning/01-adopted/spec.md",
    )
    assert resolved == (tmp_path / ".shipwright" / "planning" / "01-adopted" / "spec.md").resolve()


def test_resolve_spec_path_within_root_refuses_a_traversal(tmp_path):
    with pytest.raises(LayerCellWriteError, match="outside"):
        resolve_spec_path_within_root(tmp_path, "../../etc/passwd")


@pytest.mark.parametrize("value", [
    "unit",
    "unit, e2e",
    "a|b",
    "a\\b",
    "a\\|b",
    "line1\nline2",
    "line1\r\nline2",
    "trailing\\\\",
    "",
])
def test_escape_cell_mirrors_markdown_table(value):
    # See module docstring: fr_layer_cell_writer._escape_cell is a pinned MIRROR
    # of markdown_table.escape_cell (deliberately not an import, ADR-045
    # cross-directory-import fragility). A round-trip probe against the real
    # producer is what a prior probe (fr_table_shape's own docstring) found the
    # doubled-backslash defect with, so the pin runs the same class of input.
    from lib.fr_layer_cell_writer import _escape_cell
    assert _escape_cell(value) == escape_cell(value)


def _load_compliance_parse_layers():
    """Cross-import ``_requirement_parse._parse_layers`` for THIS test only
    (module docstring: not a runtime import — ``lib/`` cannot reach across
    the plugin boundary, ADR-045). Loaded under a synthetic package name,
    never ``scripts``/``lib`` themselves, so it cannot collide with the
    ``scripts``/``lib`` names ``shared/tests`` already bound this session —
    the exact hazard the repo-root conftest's one-test-root-per-process
    guard documents (a REGULAR package caches under whichever ``sys.path``
    entry wins first; a later insert cannot re-resolve it)."""
    collectors_dir = (
        Path(__file__).resolve().parents[2]
        / "plugins" / "shipwright-compliance" / "scripts" / "lib" / "collectors"
    )
    pkg_name = "_p35_stage4_mirror_test_collectors"
    if pkg_name not in sys.modules:
        # A NAMESPACE package (no loader, so the REAL `collectors/__init__.py`
        # never executes -- it does its own `from ..X import` reaching a
        # level this synthetic single-level parent does not have). Only
        # `_requirement_parse.py` + its own single-dot `_lib_loader` sibling
        # import need to resolve, and both live directly in this directory.
        pkg_spec = importlib.machinery.ModuleSpec(
            pkg_name, loader=None, is_package=True,
        )
        pkg_spec.submodule_search_locations = [str(collectors_dir)]
        pkg = importlib.util.module_from_spec(pkg_spec)
        sys.modules[pkg_name] = pkg
    mod = importlib.import_module(f"{pkg_name}._requirement_parse")
    return mod._parse_layers


# Separator matrix (comma, space, slash, pipe, the (inferred) marker, mixed
# case, an unrecognised token) -- Medium finding, Stage-4 code-review, P3.5
# post-push round: `live_declared_layers`'s `_LAYER_TOKEN_RE` is a pinned
# MIRROR of `_requirement_parse._parse_layers`'s own regex (see module
# docstring + `_LAYER_TOKEN_RE`'s own comment), unlike this file's sibling
# mirror (`_escape_cell`, tested above), it had no drift-pinning test at all.
@pytest.mark.parametrize("cell,expected", [
    ("unit,e2e", ["unit", "e2e"]),
    ("unit e2e", ["unit", "e2e"]),
    ("unit/e2e", ["unit", "e2e"]),
    ("unit|e2e", ["unit", "e2e"]),
    ("unit, e2e (inferred)", ["unit", "e2e"]),
    ("UNIT, E2E", ["unit", "e2e"]),
    ("unit, bogus, e2e", ["unit", "e2e"]),
    ("unit,,e2e", ["unit", "e2e"]),
    ("unit  e2e", ["unit", "e2e"]),
    ("", []),
    ("bogus", []),
])
def test_live_declared_layers_mirrors_requirement_parse_tokeniser(cell, expected):
    from lib import requirement_model
    from lib.fr_layer_cell_writer import _escape_cell

    # A literal "|" is the table's OWN column delimiter -- a real spec.md
    # round-trips a pipe separator inside a cell only escaped (`\|`), same as
    # `write_layers_cell`'s own writes. Un-escaped, the reader would see it
    # as an extra column, not a value inside this one.
    row = f"| FR-01.01 | Adopted | x | Must | y. | code | {_escape_cell(cell)} |"
    doc = "\n".join(["# Spec", "", FR_TABLE_HEADER, FR_TABLE_SEPARATOR, row, ""])

    live = live_declared_layers(doc, "FR-01.01")
    assert live == expected

    parse_layers = _load_compliance_parse_layers()
    mirrored = list(parse_layers(cell, requirement_model))
    assert live == mirrored


# Medium finding, Stage-3 doubt-review round 2, P3.5 post-push round:
# "widen never narrow" holds over the canonical layer SET a promotion
# computes, not over the cell's raw TEXT -- render_layers regenerates the
# whole cell from that set alone, silently deleting any hand-added
# annotation or non-canonical token with no warning unless a caller checks
# first.
@pytest.mark.parametrize("cell,has_residual", [
    ("unit (inferred)", False),
    ("unit, integration (inferred)", False),
    ("unit, db (inferred)", True),  # a non-canonical token
    ("unit (inferred) - integration deferred, see ADR-031", True),  # a hand note
    ("", False),
    ("bogus", True),  # zero canonical tokens, but not empty
])
def test_live_cell_has_non_canonical_content(cell, has_residual):
    from lib.fr_layer_cell_writer import _escape_cell

    row = f"| FR-01.01 | Adopted | x | Must | y. | code | {_escape_cell(cell)} |"
    doc = "\n".join(["# Spec", "", FR_TABLE_HEADER, FR_TABLE_SEPARATOR, row, ""])
    assert live_cell_has_non_canonical_content(doc, "FR-01.01") is has_residual


def test_live_cell_has_non_canonical_content_is_false_for_a_missing_row():
    assert live_cell_has_non_canonical_content(_DOC, "FR-99.99") is False

"""The converged FR-table shape: canonical header, Layers marker, rendered Area.

Campaign "Requirements Catalog", sub-iterate S5. These pin the producer side of
the contract ``fr_table_reader`` reads — the half that used to be string literals
scattered across two generators.

@FR-01.02
@FR-01.13
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))

from fr_table_shape import (  # noqa: E402
    FR_TABLE_COLUMNS,
    FR_TABLE_HEADER,
    FR_TABLE_SEPARATOR,
    INFERRED_MARKER,
    area_for,
    group_of,
    has_inferred_marker,
    label_of_split,
    render_layers,
    split_group,
)


# ---------------------------------------------------------------------------
# The canonical header
# ---------------------------------------------------------------------------


def test_the_canonical_header_is_the_shape_the_campaign_decided() -> None:
    """SPEC §3.1, verbatim. A change here is a change to every producer."""
    assert FR_TABLE_HEADER == "| ID | Area | Name | Priority | Description | Basis | Layers |"
    assert FR_TABLE_COLUMNS == (
        "ID", "Area", "Name", "Priority", "Description", "Basis", "Layers",
    )


def test_the_separator_has_one_cell_per_column() -> None:
    """A separator short by one column silently truncates the table in viewers."""
    assert FR_TABLE_SEPARATOR.count("---") == len(FR_TABLE_COLUMNS)


def test_the_header_is_readable_by_the_reader_that_consumes_it() -> None:
    """Producer and consumer agree — the round trip the two halves exist for."""
    from fr_table_reader import read_fr_rows

    doc = (
        f"{FR_TABLE_HEADER}\n{FR_TABLE_SEPARATOR}\n"
        "| FR-01.01 | Adopted | Login | Must | Users sign in | interview | unit (inferred) |\n"
    )
    (row,) = read_fr_rows(doc)
    assert row.id == "FR-01.01"
    assert row.name == "Login"
    assert row.text == "Users sign in"
    assert row.priority == "Must"
    assert row.basis_cell == "interview"
    assert row.basis_from_named_col is True
    assert row.layers_from_named_col is True


# ---------------------------------------------------------------------------
# The (inferred) marker
# ---------------------------------------------------------------------------


def test_render_layers_separates_the_marker_with_a_space() -> None:
    """The space is load-bearing, not cosmetic.

    A probe found that ``unit(inferred)`` parses to ZERO required layers: the
    consumer tokenises on ``[,\\s/|]+``, so a glued marker makes the layer name
    part of one unrecognised token and the requirement silently loses its
    coverage requirement while keeping advisory provenance. This is why callers
    never hand-format the cell.
    """
    assert render_layers(("unit",), inferred=True) == "unit (inferred)"
    assert render_layers(("unit", "e2e"), inferred=True) == "unit, e2e (inferred)"
    assert " " + INFERRED_MARKER in render_layers(("unit",), inferred=True)


def test_a_duplicate_governed_column_resolves_to_the_first(tmp_path) -> None:
    """A later duplicate must NOT silently overwrite an earlier governed column.

    Found by external review on the current head. The column map was a dict
    comprehension, so a second `Layers` column won — and a table whose first
    Layers cell read `unit (inferred)` while a duplicate read `unit, e2e`
    selected the duplicate and flipped the requirement into `explicit`
    provenance, i.e. into the unbypassable hard-gate regime, saying nothing.
    First-wins also matches the rule `pick` already applies across synonyms.
    """
    from fr_table_reader import read_fr_rows

    doc = (
        "| ID | Area | Name | Priority | Description | Basis | Layers | Layers |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| FR-01.01 | A | Login | Must | d | code | unit (inferred) | unit, e2e |\n"
    )
    (row,) = read_fr_rows(doc)
    assert row.layers_cell == "unit (inferred)"
    assert has_inferred_marker(row.layers_cell)

    # Same hazard one level up: `Layer` and `Layers` are SYNONYMS, so the table's
    # column order must decide, not the order of the synonym tuple. Found by the
    # Codex leg — `pick` preferred "layers" over "layer" regardless of position.
    synonyms = (
        "| ID | Area | Name | Priority | Description | Basis | Layer | Layers |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| FR-01.01 | A | Login | Must | d | code | unit (inferred) | unit |\n"
    )
    (row_syn,) = read_fr_rows(synonyms)
    assert row_syn.layers_cell == "unit (inferred)"

    dup_basis = (
        "| ID | Area | Name | Priority | Description | Basis | Basis | Layers |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| FR-01.01 | A | Login | Must | d | code | nonsense | unit (inferred) |\n"
    )
    (row2,) = read_fr_rows(dup_basis)
    assert row2.basis_cell == "code"


def test_a_glued_marker_swallows_the_layer_it_touches() -> None:
    """The defect ``render_layers`` exists to prevent, pinned as a FACT.

    ``unit,e2e(inferred)`` tokenises to ``["unit", "e2e(inferred)"]``, so ``e2e``
    is silently dropped while the row still looks healthy — advisory provenance,
    a plausible layer list, no complaint. Pinned here so the reason
    ``render_layers`` is mandatory cannot decay into a style preference. The
    compliance side now RECORDS this (reason ``marker_glued``); see
    ``test_audit_group_i_basis`` siblings and ``_requirement_parse``.
    """
    import re

    tokens = re.split(r"[,\s/|]+", "unit,e2e(inferred)")
    assert tokens == ["unit", "e2e(inferred)"]
    assert "e2e" not in tokens
    # And the sanctioned writer never produces it.
    assert render_layers(("unit", "e2e"), inferred=True) == "unit, e2e (inferred)"


def test_render_layers_without_the_marker_is_an_author_declaration() -> None:
    """A bare cell is `explicit` provenance — the binding, hard-gated form."""
    assert render_layers(("unit", "e2e"), inferred=False) == "unit, e2e"
    assert not has_inferred_marker(render_layers(("unit",), inferred=False))


def test_render_layers_with_no_layers_still_emits_the_marker() -> None:
    """Bare marker, not an empty cell: an empty cell is re-inferred from the title."""
    assert render_layers((), inferred=True) == INFERRED_MARKER
    assert render_layers((), inferred=False) == ""


@pytest.mark.parametrize("cell", [
    "unit (inferred)", "unit (INFERRED)", "unit ( inferred )", "(inferred)",
])
def test_the_marker_is_matched_case_insensitively_and_with_inner_space(cell: str) -> None:
    assert has_inferred_marker(cell)


@pytest.mark.parametrize("cell", [
    "unit, e2e (auto)", "unit, e2e", "unit (guess)", "inferred", "unit inferred",
])
def test_only_the_parenthesised_word_counts_as_the_marker(cell: str) -> None:
    """Narrow by design: a near-miss must NOT silently escape the hard gate."""
    assert not has_inferred_marker(cell)


# ---------------------------------------------------------------------------
# Area — rendered from the group digit (D7)
# ---------------------------------------------------------------------------


def test_group_is_read_only_from_the_canonical_id_form() -> None:
    assert group_of("FR-01.07") == "01"
    assert group_of("FR-12.34") == "12"
    for loose in ("FR-1.1", "FR-7", "FR-01.100", "QR-01.01", ""):
        assert group_of(loose) is None, loose


def test_split_label_is_the_directory_name_without_its_digits() -> None:
    assert label_of_split("01-adopted") == "Adopted"
    assert label_of_split("03-payments-api") == "Payments Api"
    assert label_of_split("02_data_model") == "Data Model"
    assert split_group("01-adopted") == "01"
    assert split_group("adopted") is None


def test_area_uses_the_split_label_when_the_split_declares_the_ids_group() -> None:
    assert area_for("FR-01.07", "01-adopted") == "Adopted"
    assert area_for("FR-03.01", "03-payments-api") == "Payments Api"


def test_a_misfiled_requirement_renders_its_own_group_not_the_folders() -> None:
    """D7: the id is authoritative, so the folder cannot quietly rename a group.

    The plain ``Group NN`` label reads as unnamed rather than as a claim, and it
    puts the inconsistency in the rendered table where someone will see it.
    """
    assert area_for("FR-02.01", "01-adopted") == "Group 02"


def test_a_noncanonical_id_falls_back_to_the_split_label() -> None:
    """No group to be authoritative with, so the only fact available is used."""
    assert area_for("FR-1.1", "01-adopted") == "Adopted"

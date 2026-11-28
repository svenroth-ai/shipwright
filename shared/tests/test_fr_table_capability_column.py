"""Every reader of the FR table takes a spec WITH and WITHOUT the optional
``Capability`` column (intent pyramid U1a). The same two FR rows are rendered in
both shapes and every inventoried reader must return the same answer for both.
"""

from __future__ import annotations

import pytest

from lib import ac_catalog, fr_scope_check
from lib.drift_parsers import parse_fr_table as drift_parse_fr_table
from lib.fr_layer_cell_writer import (
    LayerCellWriteError,
    live_required_layers,
    write_layers_cell,
)
from lib.fr_table_reader import read_fr_rows
from lib.fr_table_shape import (
    FR_TABLE_COLUMNS,
    FR_TABLE_COLUMNS_WITH_CAPABILITY,
    FR_TABLE_HEADER,
    FR_TABLE_HEADER_WITH_CAPABILITY,
    FR_TABLE_SEPARATOR,
    FR_TABLE_SEPARATOR_WITH_CAPABILITY,
    columns_of_canonical_header,
)
from tools.grill_trace_fr_coverage import extract_fr_names, extract_fr_rows
from tools.verifiers._baseline_label_hits import _spec_lines
from tools.verifiers._baseline_touch_spec import fr_digests

pytestmark = pytest.mark.covers("FR-01.16/AC02")


_ROWS = [
    ("FR-01.01", "Core", "Sign in", "Must", "A user signs in.", "interview", "unit"),
    ("FR-01.02", "Core", "Sign out", "Should", "A user signs out.", "code", "unit, e2e (inferred)"),
]


def _spec(with_capability: bool, capability: str = "CAP-01") -> str:
    header = FR_TABLE_HEADER_WITH_CAPABILITY if with_capability else FR_TABLE_HEADER
    sep = FR_TABLE_SEPARATOR_WITH_CAPABILITY if with_capability else FR_TABLE_SEPARATOR
    lines = ["# Spec", "", "## Functional Requirements", "", header, sep]
    for fr_id, area, name, prio, desc, basis, layers in _ROWS:
        cells = [fr_id, area, *([capability] if with_capability else []), name, prio, desc, basis, layers]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


BOTH = pytest.mark.parametrize("with_capability", [False, True], ids=["no-column", "with-column"])


def test_with_capability_columns_differ_from_canonical_only_by_the_one_column():
    assert FR_TABLE_COLUMNS_WITH_CAPABILITY[:2] == FR_TABLE_COLUMNS[:2]
    assert FR_TABLE_COLUMNS_WITH_CAPABILITY[2] == "Capability"
    assert FR_TABLE_COLUMNS_WITH_CAPABILITY[3:] == FR_TABLE_COLUMNS[2:]
    assert columns_of_canonical_header(FR_TABLE_HEADER + "  ") == FR_TABLE_COLUMNS
    assert columns_of_canonical_header(FR_TABLE_HEADER_WITH_CAPABILITY) == FR_TABLE_COLUMNS_WITH_CAPABILITY
    assert columns_of_canonical_header("| ID | Name | Priority |") is None


@BOTH
def test_fr_table_reader_reads_every_field(with_capability):
    rows = read_fr_rows(_spec(with_capability))
    assert [(r.id, r.name, r.text, r.priority, r.layers_cell, r.basis_cell) for r in rows] == [
        ("FR-01.01", "Sign in", "A user signs in.", "Must", "unit", "interview"),
        ("FR-01.02", "Sign out", "A user signs out.", "Should", "unit, e2e (inferred)", "code"),
    ]
    assert all(r.layers_from_named_col and r.basis_from_named_col for r in rows)


@BOTH
def test_drift_parser_projection(with_capability):
    got = drift_parse_fr_table(_spec(with_capability), "01-core", "spec.md")
    assert [(f.id, f.text, f.priority) for f in got] == [
        ("FR-01.01", "A user signs in.", "Must"),
        ("FR-01.02", "A user signs out.", "Should"),
    ]


@BOTH
def test_ac_catalog_area_and_description(with_capability):
    assert ac_catalog.parse_fr_table(_spec(with_capability)) == {
        "FR-01.01": {"area": "Core", "description": "A user signs in."},
        "FR-01.02": {"area": "Core", "description": "A user signs out."},
    }


@BOTH
def test_fr_scope_check_priority_and_name(with_capability):
    priority, removed, names = fr_scope_check._scan_table(_spec(with_capability))
    assert priority == {"FR-01.01": "must", "FR-01.02": "should"}
    assert names == {"FR-01.01": "Sign in", "FR-01.02": "Sign out"}
    assert removed == set()


@BOTH
def test_grill_trace_name_and_basis(with_capability):
    spec = _spec(with_capability)
    assert extract_fr_names(spec) == {"FR-01.01": "Sign in", "FR-01.02": "Sign out"}
    assert extract_fr_rows(spec) == {
        "FR-01.01": ("Sign in", "interview"),
        "FR-01.02": ("Sign out", "code"),
    }


@BOTH
def test_layer_cell_writer_rewrites_only_the_layers_cell(with_capability):
    spec = _spec(with_capability)
    out = write_layers_cell(spec, "FR-01.01", "unit, e2e")
    assert live_required_layers(out, "FR-01.01") == ["unit", "e2e"]
    assert [r.name for r in read_fr_rows(out)] == ["Sign in", "Sign out"]
    changed = [(a, b) for a, b in zip(spec.splitlines(), out.splitlines()) if a != b]
    assert len(changed) == 1
    # the capability cell survives the rewrite untouched
    assert ("CAP-01" in changed[0][1]) is with_capability
    assert write_layers_cell(out, "FR-01.01", "unit, e2e") == out  # idempotent


def test_layer_cell_writer_still_refuses_two_candidate_headers_across_shapes():
    doc = _spec(False) + "\n" + _spec(True).replace("FR-01.0", "FR-02.0")
    with pytest.raises(LayerCellWriteError, match="refusing to guess which one"):
        write_layers_cell(doc, "FR-01.01", "unit, e2e")


def test_layer_cell_writer_refuses_a_row_with_the_wrong_cell_count_for_its_header():
    spec = _spec(True).replace("| CAP-01 ", "", 1)  # row loses its Capability cell
    with pytest.raises(LayerCellWriteError, match="cell"):
        write_layers_cell(spec, "FR-01.01", "unit, e2e")


@BOTH
def test_label_hit_scan_keeps_description_and_drops_bookkeeping(with_capability):
    lines = _spec_lines(_spec(with_capability), "FR-01.01")
    assert any("A user signs in." in line for line in lines)
    assert not any("interview" in line or "unit" in line for line in lines)
    assert not any("CAP-01" in line for line in lines)


@BOTH
def test_label_hit_scan_sees_a_description_edit(with_capability):
    base = _spec(with_capability)
    head = base.replace("A user signs in.", "A user signs in with a passkey.")
    assert _spec_lines(base, "FR-01.01") != _spec_lines(head, "FR-01.01")


def test_a_capability_reassignment_is_not_a_normative_text_change():
    a, b = _spec(True, "CAP-01"), _spec(True, "CAP-07")
    assert fr_digests(a) == fr_digests(b)
    assert _spec_lines(a, "FR-01.01") == _spec_lines(b, "FR-01.01")
    assert fr_digests(_spec(False)) == fr_digests(a)


def test_a_blank_capability_cell_leaves_the_digest_and_a_normative_edit_changes_it():
    blank = _spec(True, "")
    assert fr_digests(blank) == fr_digests(_spec(False))
    edited = _spec(True).replace("A user signs in.", "A user signs in with a passkey.")
    assert fr_digests(edited)["FR-01.01"] != fr_digests(_spec(True))["FR-01.01"]
    assert fr_digests(edited)["FR-01.02"] == fr_digests(_spec(True))["FR-01.02"]


def test_a_status_only_change_is_a_noop_in_both_baseline_modules():
    base = _spec(True).replace("| Layers |", "| Layers | Status |", 1)
    base = base.replace("|---|---|---|---|---|---|---|---|", "|---|---|---|---|---|---|---|---|---|", 1)
    base = base.replace("unit |\n", "unit | open |\n", 1).replace("(inferred) |\n", "(inferred) | open |\n")
    head = base.replace("| open |", "| done |")
    assert _spec_lines(base, "FR-01.01") == _spec_lines(head, "FR-01.01")
    assert fr_digests(base) == fr_digests(head)


def test_label_hit_columns_do_not_leak_past_the_table_that_declared_them():
    legacy_row = "| FR-01.03 | Core | Export | Must | Exports data. | code | unit |"
    doc = _spec(True) + "\n## Later section\n\n" + legacy_row + "\n"
    lines = _spec_lines(doc, "FR-01.03")
    assert "FR-01.03|Core|Export|Must|Exports data." in lines  # first five cells, not the header's indices


@BOTH
def test_blind_label_pack_catalog_reads_name_and_statement(with_capability):
    from tools.verifiers._baseline_b_packs import catalog

    got = catalog(_spec(with_capability))
    assert [(c["id"], c["name"], c["statement"]) for c in got] == [
        ("FR-01.01", "Sign in", "A user signs in."),
        ("FR-01.02", "Sign out", "A user signs out."),
    ]


def test_label_hit_columns_survive_a_later_heading_and_agree_with_the_digest():
    late = "| FR-01.03 | Core | CAP-01 | Export | Must | Exports data. | code | unit |"
    spec = _spec(True) + "\n### Later notes\n\n" + late + "\n"
    lines = _spec_lines(spec, "FR-01.03")
    # the row appears ONLY under the later heading: it is governed by the 8-column header kept across it
    assert "FR-01.03|Core|Export|Must|Exports data." in lines
    assert not any("CAP-01" in line for line in lines)
    edited = spec.replace("Exports data.", "Exports data as CSV.")
    assert _spec_lines(spec, "FR-01.03") != _spec_lines(edited, "FR-01.03")
    moved = spec.replace("| CAP-01 | Export", "| CAP-09 | Export")
    assert _spec_lines(spec, "FR-01.03") == _spec_lines(moved, "FR-01.03")
    assert fr_digests(spec)["FR-01.03"] != fr_digests(edited)["FR-01.03"]

"""Boundary probes for the one FR-table reader (``references/boundary-probes.md``).

Split out of ``test_fr_table_reader_contract.py`` at the cohesive seam rather
than baselined past the size cap: that module asserts the reader's SHAPE
contract (which table layouts parse, what the seven convergence rules decided),
while this one asserts its robustness at the input boundary — the encoding,
line-ending and stray-character categories a spec.md picks up from the
filesystem and from human editing.

Carried over in intent from the retired ``test_fr_table_drift_protection.py``.
Two changes worth naming: the probes now run against parsed ROWS rather than a
regex match object, and the "pipe inside a cell" case is no longer filed as a
known limitation — convergence rule C4 handles it, and its probe lives with the
other C-rules in the contract module.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))

from fr_table_reader import read_fr_rows  # noqa: E402

_HEADER = "| ID | Requirement | Priority |\n"


def _one(text: str):
    rows = read_fr_rows(text)
    assert len(rows) == 1, [r.id for r in rows]
    return rows[0]


def test_probe_utf8_bom_at_file_start():
    """A BOM lands on the first line, not on the table — but a reader that
    matched the whole file as one string could still be tripped by it."""
    assert [r.id for r in read_fr_rows(
        "﻿# Specification\n" + _HEADER + "| FR-01.01 | login | Must |\n"
    )] == ["FR-01.01"]


def test_probe_bom_directly_before_the_header_row():
    """The sharper case: the BOM sits on the HEADER line itself, so a reader
    comparing ``cells[0] == "id"`` would see ``"\\ufeffid"`` and silently map
    nothing. That failure mode is exactly FV-4, reached by a different route."""
    rows = read_fr_rows("﻿" + _HEADER + "| FR-01.01 | login | Must |\n")
    assert [(r.id, r.text) for r in rows] == [("FR-01.01", "login")]


def test_probe_crlf_line_endings():
    """Windows checkouts with ``core.autocrlf=true`` routinely produce these."""
    assert [r.id for r in read_fr_rows(
        "| ID | Requirement | Priority |\r\n| FR-01.01 | login | Must |\r\n"
    )] == ["FR-01.01"]


def test_probe_crlf_does_not_leak_into_the_last_cell():
    """A trailing ``\\r`` surviving into the value would poison every downstream
    string comparison — manifest keys, RTM cells, ``@FR`` tag matching."""
    assert _one(
        "| ID | Requirement | Priority | Layers |\r\n"
        "| FR-01.01 | login | Must | unit |\r\n"
    ).layers_cell == "unit"


def test_probe_non_ascii_in_the_body():
    assert _one(
        "| ID | Name | Priority | Description | Source |\n"
        "| FR-02.99 | /übung | Must | Umlaute — Leerzeichen + 中文. | e.json |\n"
    ).text == "Umlaute — Leerzeichen + 中文."


def test_probe_literal_hash_in_the_body():
    """Table cells have no ``# comment`` semantics — "fixes #42" must survive."""
    assert _one(
        _HEADER + "| FR-03.01 | Refers to issue #42 in tracker | Should |\n"
    ).text == "Refers to issue #42 in tracker"


def test_probe_a_hash_starting_a_cell_is_not_a_heading():
    """``#`` at the start of a CELL must not be mistaken for a markdown heading
    and reset the parse state."""
    assert _one(
        _HEADER + "| FR-03.02 | #42 tracked upstream | Should |\n"
    ).text == "#42 tracked upstream"


def test_probe_trailing_whitespace_after_the_closing_pipe():
    """File formatters insert it routinely."""
    assert [r.id for r in read_fr_rows(
        _HEADER + "| FR-01.01 | login | Must |    \n"
    )] == ["FR-01.01"]


def test_probe_empty_cells_do_not_shift_the_columns():
    assert _one(
        "| ID | Requirement | Priority | Layers |\n"
        "| FR-01.01 |  | Must |  |\n"
    ).text == ""


def test_probe_separator_row_is_neither_a_requirement_nor_a_header():
    """The dashes row names no Priority column, so it cannot be read as a
    header — if it were, it would clobber the real map with junk names."""
    assert _one(
        _HEADER + "|----|-------------|----------|\n| FR-01.01 | login | Must |\n"
    ).text == "login"


def test_probe_an_empty_document_yields_no_rows():
    assert read_fr_rows("") == []


def test_probe_prose_mentioning_an_fr_id_is_not_a_row():
    """Requirement ids appear constantly in prose, ADR text and commit
    references. Only a table row declares one."""
    assert read_fr_rows(
        "FR-01.01 is described below, superseding FR-01.02.\n"
        "See `FR-01.03` for the migration note.\n"
    ) == []


# ---------------------------------------------------------------------------
# Id validation is a FULL match on a trimmed cell, not a search or a prefix.
# Raised in external plan review (GPT, high): calling a regex "strict" does not
# by itself guarantee full-cell validation, and an unanchored use would let
# `FR-01.01-extra` through and re-open the loose behaviour S4 converged away.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cell", [
    "FR-01.01-extra",
    "FR-01.011",
    "xFR-01.01",
    "FR-01.01x",
    "`FR-01.01`",
    "FR-01.01 and FR-01.02",
    "FR-1.1",
    "FR-7",
    "FR-001.001",
])
def test_probe_near_miss_ids_are_not_requirement_rows(cell: str):
    assert read_fr_rows(f"{_HEADER}| {cell} | body | Must |\n") == []


@pytest.mark.parametrize("cell", ["FR-01.01", "  FR-01.01  ", "FR-99.99"])
def test_probe_a_padded_canonical_id_is_still_canonical(cell: str):
    """Cells are trimmed before matching, so table alignment padding is fine."""
    assert [r.id for r in read_fr_rows(
        f"{_HEADER}|{cell}| body | Must |\n"
    )] == [cell.strip()]


def test_probe_a_persisted_column_map_does_not_capture_an_unrelated_table():
    """Raised in external plan review (GPT, high; Gemini, high).

    The column map survives headings by design — that is the FV-5 fix — so the
    obvious worry is that it then swallows rows of some unrelated later table.
    It cannot: a row is only a requirement when its FIRST cell is a canonical
    id. An FR id sitting in any other column is data, not a declaration.
    """
    text = (
        _HEADER
        + "| FR-01.01 | real requirement | Must |\n"
        + "\n## Coverage summary\n\n"
        + "| Test | Covers | Result |\n"
        + "| t_login | FR-01.01 | pass |\n"
        + "| t_logout | FR-01.02 | fail |\n"
    )
    assert [(r.id, r.text) for r in read_fr_rows(text)] == [
        ("FR-01.01", "real requirement"),
    ]


# ---------------------------------------------------------------------------
# Escaping round-trip (convergence rule C4). Raised in external plan review
# (GPT, medium): state the unescape contract precisely and probe its corners.
# The producer is shared/scripts/markdown_table.escape_cell.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    (r"a \| b", "a | b"),
    (r"\| leading", "| leading"),
    (r"a \| b \| c", "a | b | c"),
    # A backslash that does not begin an escape pair is content, so a
    # hand-written path survives untouched.
    (r"C:\repo\spec", r"C:\repo\spec"),
    # `\\` IS an escape pair -- it is what escape_cell emits for one literal
    # backslash, so undoing it is what makes the round-trip exact. The declared
    # cost: a HAND-written literal `\\` reads as one backslash, because that is
    # what the producer means by it. (This expectation changed during S4: it
    # previously asserted `\\` stayed doubled, which was the doubled-backslash
    # defect the producer round-trip probe found.)
    ("ends with a backslash \\\\", "ends with a backslash \\"),
    (r"100% \| done", "100% | done"),
])
def test_probe_escaped_pipe_unescaping(raw: str, expected: str):
    row = _one(f"{_HEADER}| FR-01.01 | {raw} | Must |\n")
    assert row.text == expected


@pytest.mark.parametrize("value", [
    "plain",
    "a | b",
    "a || b",
    "C:\\repo\\spec",
    "ends with backslash \\",
    "a\\|b",               # a literal backslash immediately before a pipe
    "a\\\\|b",
    "pipe at end |",
    "| pipe at start",
    "\\\\server\\share",
    "100% | done",
    "  padded  ",
])
def test_producer_consumer_round_trip(value: str):
    """The real ADR-024 round-trip: PRODUCER -> table -> CONSUMER.

    Every other escaping test here hand-writes the escaped form, which only ever
    proves the reader agrees with the test author. This one runs the value
    through ``markdown_table.escape_cell`` — the actual producer — and asserts
    the reader hands back what went in.

    It is not decoration. Written as a probe during S4's confidence-calibration
    step, it failed 4 of 12 cases on the first run: ``escape_cell`` emits
    ``\\`` -> ``\\\\`` BEFORE ``|`` -> ``\\|``, and a reader that undid only the
    pipe returned every backslash in the value doubled. Any Description holding
    a path or a regex was affected. Four of the five parsers S4 replaced had
    the same defect and no round-trip test to reveal it.
    """
    sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
    from markdown_table import escape_cell  # noqa: PLC0415

    text = f"{_HEADER}| FR-01.01 | {escape_cell(value)} | Must |\n"
    assert _one(text).text == value.strip()


# Thin rows (convergence rule C8) moved to test_fr_table_reader_boundaries.py
# when external code review re-decided the rule: a row that cannot reach its
# header's Priority column is now recorded, not emitted.


def test_probe_an_escaped_pipe_does_not_shift_the_priority_column():
    """The failure this closes: four of the five readers split on the escaped
    pipe, so the cell count grew by one and everything after it moved."""
    row = _one(
        "| ID | Requirement | Priority | Layers |\n"
        + r"| FR-01.01 | a \| b | Should | unit |" + "\n"
    )
    assert (row.text, row.priority, row.layers_cell) == ("a | b", "Should", "unit")

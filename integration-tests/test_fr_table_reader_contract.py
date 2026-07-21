"""The FR-table reader's contract: five shapes, seven convergence rules, probes.

Replaces ``test_fr_table_drift_protection.py``. That suite ran the same fixtures
through the TWO duplicated FR-table regexes so a fix landing in only one would
fail — necessary while the duplication existed, meaningless now that campaign S4
left one implementation. Worth recording what it did NOT cover, because the gap
is the reason S4 was needed at all: it pinned only the two REGEXES. The
removed-section loops around them were semantic clones that nothing checked, and
neither were the three header-driven parsers in scope. A drift guard over 2 of 5
implementations, on 1 of 2 halves each, read as protection.

What replaces it is a contract on the one reader:

* every historical table shape still parses (the ADR-031 regression class);
* the ``## Removed Requirements`` section — the half the old suite never
  reached;
* each of the seven convergence rules, because each replaced two or three
  different answers and a silent revert to any of them is a real regression;
* the boundary probes, carried over verbatim in intent (BOM, CRLF, non-ASCII,
  literal ``#``, whitespace, and the pipe-in-a-cell case that used to be
  documented as a known limitation and is now simply handled).

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))

from fr_table_reader import read_active_fr_rows, read_fr_rows  # noqa: E402


def _one(text: str):
    rows = read_fr_rows(text)
    assert len(rows) == 1, [r.id for r in rows]
    return rows[0]


# ---------------------------------------------------------------------------
# The five historical shapes (campaign SPEC section 2.1)
# ---------------------------------------------------------------------------

SHAPES = [
    pytest.param(
        "| ID | Requirement | Priority | Layers |\n"
        "| FR-01.01 | User can log in | Must | unit, e2e |\n",
        ("FR-01.01", "User can log in", "Must", "unit, e2e"),
        id="greenfield-template",
    ),
    pytest.param(
        "| ID | Requirement | Priority |\n"
        "| FR-02.01 | Dashboard shows activity | Should |\n",
        ("FR-02.01", "Dashboard shows activity", "Should", ""),
        id="greenfield-example-no-layers",
    ),
    pytest.param(
        "| ID | Name | Priority | Description | Source |\n"
        "| FR-01.01 | /run | Must | Orchestrate the pipeline. | enrichment.json |\n",
        ("FR-01.01", "Orchestrate the pipeline.", "Must", ""),
        id="adopt-5col-on-disk",
    ),
    pytest.param(
        "| ID | Name | Priority | Description | Source | Layers |\n"
        "| FR-04.01 | /test | May | Run the suites. | enrichment.json | unit |\n",
        ("FR-04.01", "Run the suites.", "May", "unit"),
        id="adopt-6col-writer",
    ),
    pytest.param(
        "| FR | Description | Priority | Layers |\n"
        "| FR-05.01 | Coverage per layer | Must | unit |\n",
        ("FR-05.01", "Coverage per layer", "Must", "unit"),
        id="traceability-fixture-fr-header",
    ),
]


@pytest.mark.parametrize("text, expected", SHAPES)
def test_every_historical_shape_parses(text: str, expected):
    row = _one(text)
    assert (row.id, row.text, row.priority, row.layers_cell) == expected


def test_column_order_is_not_load_bearing():
    """The FV-1 trigger. The old regex pinned Must|Should|May to data column 3,
    so a reordered table yielded zero rows and traceability check T1 SKIPped a
    project whose requirements were entirely uncovered."""
    row = _one(
        "| ID | Priority | Requirement | Layers |\n"
        "| FR-06.01 | Must | Reordered but still a requirement | unit |\n"
    )
    assert (row.text, row.priority, row.layers_cell) == (
        "Reordered but still a requirement", "Must", "unit",
    )


def test_a_row_wider_than_its_header_does_not_shift_the_body():
    """FV-3 — the strongest single argument for the whole change: this used to
    put live WRONG text in a shipped RTM."""
    assert _one(
        "| ID | Requirement | Priority |\n"
        "| FR-07.01 | ok | Should | extra | cells |\n"
    ).text == "ok"


# ---------------------------------------------------------------------------
# The removed-section half the old suite never reached
# ---------------------------------------------------------------------------

_WITH_REMOVED = (
    "## Requirements\n"
    "| ID | Requirement | Priority |\n"
    "| FR-01.01 | Live one | Must |\n"
    "\n"
    "### Removed Requirements\n"
    "| ID | Requirement | Priority |\n"
    "| FR-01.09 | Retired one | Must |\n"
    "\n"
    "## Next\n"
    "| FR-01.20 | After the removed section | Must |\n"
)


def test_removed_rows_are_marked_not_dropped():
    assert {r.id: r.status for r in read_fr_rows(_WITH_REMOVED)} == {
        "FR-01.01": "active", "FR-01.09": "removed", "FR-01.20": "active",
    }


def test_the_removed_section_ends_at_the_next_same_or_shallower_heading():
    """``## Next`` is shallower than ``### Removed Requirements``, so FR-01.20
    is live again. Getting this wrong retires every requirement in the rest of
    the file."""
    assert [r.id for r in read_active_fr_rows(_WITH_REMOVED)] == [
        "FR-01.01", "FR-01.20",
    ]


def test_an_inline_removed_marker_does_not_retire_the_requirement():
    """S3 left S4 the note that this repo's inline ``**REMOVED** by`` marker
    "still parses as active" and that the reader should recognise both removal
    forms. Investigated at S4: **the premise is falsified, and implementing it
    would delete a live requirement.**

    The one marker in this repo sits at ``01-adopted/spec.md:198``, inside the
    prose refinement section headed ``### FR-01.01 — /shipwright-run``. It
    retires a SUB-BEHAVIOUR (the multi-session execution mode), not the
    requirement: FR-01.01 is ``/shipwright-run`` itself, Must, and its table row
    is untouched. Reading the marker as a row-level tombstone would drop the
    orchestrator from every live requirement set, RTM and coverage gate.

    The writer contract has exactly one removal form — ``path-b-change.md``
    step REMOVE says to MOVE the row into a ``### Removed Requirements``
    subsection — and the marker is not it. So this pins the correct behaviour
    rather than closing the gap S3 described, because the gap was not there.
    """
    text = (
        "## Functional Requirements\n"
        "| ID | Name | Priority | Description | Source |\n"
        "| FR-01.01 | /run | Must | Orchestrate the pipeline. | e.json |\n"
        "\n"
        "### FR-01.01 — `/run` (hook ownership)\n"
        "\n"
        "**REMOVED** by `iterate-2026-07-14-remove-multi-session`: the\n"
        "multi-session execution mode.\n"
    )
    assert [(r.id, r.status) for r in read_fr_rows(text)] == [
        ("FR-01.01", "active"),
    ]


def test_fold_map_rows_are_never_requirements():
    """Load-bearing rather than cosmetic, and MORE so after rule C3: with
    invalid priorities coerced instead of dropped, an unbackticked fold table
    would otherwise resurrect every folded id as a live requirement demanding
    its own coverage."""
    text = (
        "| ID | Requirement | Priority |\n"
        "| FR-01.01 | Live | Must |\n"
        "\n"
        "## FR-Fold-Map\n"
        "\n"
        "| FR-01.30 | folded into | FR-01.01 |\n"
        "| FR-01.31 | folded into | FR-01.01 |\n"
    )
    assert [r.id for r in read_fr_rows(text)] == ["FR-01.01"]


# ---------------------------------------------------------------------------
# The seven convergence rules (ADR-031 revision). Each replaced two or three
# different answers, so each needs its own standing assertion.
# ---------------------------------------------------------------------------

def test_c1_only_the_canonical_two_digit_id_is_a_requirement_row():
    """Strictest of the three tiers, and not a preference: manifest schema v3
    derives a requirement's namespace from the id's group digits, so only this
    form makes that derivation total."""
    text = (
        "| ID | Requirement | Priority |\n"
        "| FR-01.01 | canonical | Must |\n"
        "| FR-1.1 | single digit | Must |\n"
        "| FR-7 | no dot | Must |\n"
        "| FR-001.001 | three digit | Must |\n"
    )
    assert [r.id for r in read_fr_rows(text)] == ["FR-01.01"]


def test_c2_the_column_map_survives_a_heading_and_is_replaced_by_a_header():
    """FV-5 was reset-at-every-heading; ``_requirement_parse`` never reset at
    all. One rule replaces both extremes."""
    text = (
        "| ID | Name | Priority | Description |\n"
        "| FR-01.01 | n1 | Must | d1 |\n"
        "## Some unrelated heading\n"
        "| FR-01.02 | n2 | Must | d2 |\n"
        "## Another table\n"
        "| ID | Requirement | Priority |\n"
        "| FR-01.03 | body3 | Must |\n"
    )
    rows = {r.id: (r.name, r.text) for r in read_fr_rows(text)}
    assert rows["FR-01.02"] == ("n2", "d2"), "the map must survive a heading"
    assert rows["FR-01.03"] == ("", "body3"), "a header row must replace it"


def test_c3_an_unrecognised_priority_is_coerced_not_fatal():
    """Two parsers dropped the whole row. Losing a requirement over a typo is
    the same silent-loss class the campaign exists to remove, and ``Must`` is
    the coercion that never downgrades one out of scrutiny."""
    text = (
        "| ID | Requirement | Priority |\n"
        "| FR-01.06 | lowercase | must |\n"
        "| FR-01.07 | nonsense | HIGH |\n"
    )
    assert [(r.id, r.priority) for r in read_fr_rows(text)] == [
        ("FR-01.06", "Must"), ("FR-01.07", "Must"),
    ]


def test_c4_an_escaped_pipe_is_content_not_a_cell_boundary():
    """``markdown_table.escape_cell`` is the producer for every machine-written
    cell in this repo. Four of the five readers split on it anyway and truncated
    the text; this is the round-trip closing."""
    row = _one(
        "| ID | Requirement | Priority |\n"
        r"| FR-01.08 | escaped \| pipe in text | Must |" + "\n"
    )
    assert row.text == "escaped | pipe in text"


def test_c4_a_lone_backslash_is_left_alone():
    """Only ``\\|`` is undone. A Windows path in a hand-written cell must not
    lose its separators to an over-eager inverse."""
    assert _one(
        "| ID | Requirement | Priority |\n"
        r"| FR-01.09 | see C:\repo\spec | Must |" + "\n"
    ).text == r"see C:\repo\spec"


@pytest.mark.parametrize("line, expected_id", [
    ("  | FR-01.05 | indented row | Must |", "FR-01.05"),
    ("| FR-01.02 | no closing pipe | Must", "FR-01.02"),
])
def test_c5_indentation_and_a_missing_closing_pipe_do_not_drop_a_row(
    line: str, expected_id: str,
):
    """An anchored ``^\\|`` rejects a legitimately indented GFM table."""
    text = f"| ID | Requirement | Priority |\n{line}\n"
    assert [r.id for r in read_fr_rows(text)] == [expected_id]



# C8 (thin rows) is probed in test_fr_table_reader_probes.py — it is an
# input-robustness question, and external code review found the rule as WRITTEN
# ("an id plus anything") disagreed with the code ("a canonical id is enough").


def test_layers_are_read_only_from_a_named_column():
    """Otherwise the adopt 5-column Description cell reads as a layer list."""
    row = _one(
        "| ID | Name | Priority | Description | Source |\n"
        "| FR-01.01 | /run | Must | Orchestrate | enrichment.json |\n"
    )
    assert (row.layers_cell, row.layers_from_named_col) == ("", False)


def test_an_undeclared_sibling_is_refused():
    """`_ALLOWED_SIBLINGS` makes `_sibling`'s scanner suppression a precondition
    rather than a property of its five literal call sites. Asserted per load
    style in test_fr_table_reader_load_styles.py too, but that module runs
    subprocesses by design and coverage cannot see into them.
    """
    import fr_table_reader

    with pytest.raises(ValueError, match="_ALLOWED_SIBLINGS"):
        fr_table_reader._sibling("os")

"""Where a requirements table ENDS — and what may not be read as one.

Split out of ``test_fr_table_reader_contract.py``. That module asserts what the
reader extracts from a table it has already accepted; this one asserts which
tables it accepts at all. The seam is the composition defect external code
review found on the first S4 commit, and every test here exists because of it.

**The defect.** Three individually-defensible convergence rules composed into a
false-requirement route: the column map deliberately survives a heading (C2 —
that is the FV-5 fix), an unrecognised priority is coerced rather than dropping
its row (C3), and there was no minimum row width (C8 as first written). So a
second, FR-id-keyed table under a later heading — a coverage or summary table —
parsed as requirements. Those rows reached ``build_requirement_index``, which
raises ``DuplicateRequirementId``, names the SAME file twice, and tells the
operator to "renumber one of the two rows": unactionable, because the second row
is not a requirement.

**Why it was reachable.** Every guard that independently blocked it was removed
by the same change — drift/rtm's positional ``Must|Should|May`` in column 3,
``_requirement_parse``'s three-cell floor, and group_i's reset-at-every-heading.
Three redundant guards went at once and their shared duty went with them.

``## FR-Fold-Map`` is the one FR-id-keyed table this repo already knew about,
and C7 protects it BY NAME. That C7 had to exist is itself the evidence such
tables occur; every other one was unprotected.

Two rules changed to close it, both re-decided rather than patched: **C6
(headerless positional fallback) is WITHDRAWN**, and **C8 now requires a row to
reach the Priority column its own header declares**. Nothing is dropped
silently — every declined row is recorded in the ``rejects`` accumulator.

The last three tests are the guards ON the guards: closing this route must not
re-introduce FV-5, must not let a separator row end a table, and must not let a
malformed id row end one either.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))

from fr_table_reader import read_fr_rows  # noqa: E402


def test_c6_withdrawn_a_table_with_no_header_at_all_yields_nothing():
    """C6 (headerless positional fallback) was WITHDRAWN after code review.

    It shipped in the first S4 commit over both external reviewers' objection.
    The composition route settled it: a column map that survives a heading
    (C2) plus a positional fallback is what let a coverage table keyed by FR id
    yield requirements. Both writers always emit a header, so this was a
    degraded mode rather than a format — and the row is RECORDED, not lost,
    which was the only argument for keeping it.
    """
    rejects: list = []
    assert read_fr_rows("| FR-01.01 | body | Should | unit |\n", rejects=rejects) == []
    assert [(r["id"], r["reason"]) for r in rejects] == [
        ("FR-01.01", "no_governing_header"),
    ]


def test_c8_re_decided_a_row_must_reach_its_headers_priority_column():
    """C8 (no minimum cell count) was RE-DECIDED after code review.

    The first S4 commit kept any row carrying a canonical id, on the argument
    that a text-less requirement is loud in the RTM while a dropped one is
    silent. That argument survives — the row is still reported — but "keep it as
    a REQUIREMENT" did not: a row too short to reach the Priority column its own
    header declares does not fit the shape that header claims, and admitting it
    is half of the composition route below.
    """
    rejects: list = []
    rows = read_fr_rows(
        "| ID | Requirement | Priority |\n"
        "| FR-01.01 | ragged |\n"
        "| FR-01.02 | complete | Must |\n",
        rejects=rejects,
    )
    assert [r.id for r in rows] == ["FR-01.02"]
    assert [(r["id"], r["reason"]) for r in rejects] == [
        ("FR-01.01", "row_narrower_than_header"),
    ]


def test_a_summary_table_keyed_by_fr_id_does_not_yield_requirements():
    """The composition route, closed. Found in external code review.

    C2 (the map survives a heading), C3 (coerce an unrecognised priority) and
    C8-as-first-written (no width floor) are each defensible and composed into a
    defect: a second FR-id-keyed table under a later heading parsed as
    requirements. Its rows reached `build_requirement_index`, which raises
    `DuplicateRequirementId` naming the SAME file twice and telling the operator
    to "renumber one of the two rows" — unactionable, because the second row is
    not a requirement at all.

    Every guard that independently blocked this had been removed by the same
    change: drift/rtm's positional `Must|Should|May`, `_requirement_parse`'s
    three-cell floor, and group_i's reset-at-every-heading.

    Both widths are asserted because a width bound ALONE does not close it —
    the three-column variant satisfies any floor.
    """
    for coverage_table in (
        "| FR | Result |\n| FR-01.01 | pass |\n",
        "| FR | Result | Notes |\n| FR-01.01 | pass | ok |\n",
    ):
        rows = read_fr_rows(
            "| ID | Requirement | Priority |\n"
            "| FR-01.01 | real requirement | Must |\n"
            "\n## Coverage summary\n\n" + coverage_table
        )
        assert [(r.id, r.text) for r in rows] == [
            ("FR-01.01", "real requirement"),
        ], coverage_table


def test_fv5_still_holds_a_heading_alone_does_not_end_the_table():
    """The guard on the guard: closing the composition route must not
    re-introduce FV-5 by making any heading reset the map."""
    rows = read_fr_rows(
        "| ID | Requirement | Priority |\n"
        "| FR-01.01 | first | Must |\n"
        "\n## Next\n\n"
        "| FR-01.20 | after a heading | Must |\n"
    )
    assert [r.id for r in rows] == ["FR-01.01", "FR-01.20"]


def test_a_separator_row_does_not_end_the_table():
    """A separator sits directly under every header, so treating it as "a table
    row naming no Priority column" would invalidate the map just built."""
    assert [r.id for r in read_fr_rows(
        "| ID | Requirement | Priority |\n"
        "|:---|-------------|:-------:|\n"
        "| FR-01.01 | after the separator | Must |\n"
    )] == ["FR-01.01"]


def test_a_non_canonical_id_row_does_not_end_the_table():
    """A malformed requirement row is not a header. If it invalidated the map,
    a single `FR-1.1` would silently drop every row beneath it."""
    rejects: list = []
    rows = read_fr_rows(
        "| ID | Requirement | Priority |\n"
        "| FR-01.01 | canonical | Must |\n"
        "| FR-1.1 | malformed id | Must |\n"
        "| FR-99.99 | still parsed | Must |\n",
        rejects=rejects,
    )
    assert [r.id for r in rows] == ["FR-01.01", "FR-99.99"]
    assert [(r["id"], r["reason"]) for r in rejects] == [
        ("FR-1.1", "non_canonical_id"),
    ]

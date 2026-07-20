"""TT3 — ``parse_fr_table`` tolerates the new ``Layers`` column (Spec D2).

A greenfield FR table gains a 4th ``Layers`` column; an adopt table appends it as
a 6th. The shared FR-table parser must NOT drop those rows (backward-compat with
every existing consumer) and must still extract the FR body from the correct
column. The ``required_layers`` value itself is parsed by the one requirement-model
parser (compliance ``_requirement_parse``); this shared parser only has to stop
dropping FRs that carry the column.
"""

from __future__ import annotations

from lib.drift_parsers import parse_fr_table

# S4 withdrew the headerless positional fallback (convergence rule C6), so the
# two synthetic pathological rows below need a governing header like any other
# requirement row. Their subject is scan LINEARITY, not table shape.
_HEADER = "| ID | Requirement | Priority |\n"

_4COL = """## Functional Requirements
| ID | Requirement | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.01 | User can sign in | Must | unit, e2e |
| FR-01.02 | Persist an order | Should | unit, integration |
"""

_3COL = """## Functional Requirements
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01.01 | User can sign in | Must |
"""

_6COL = """## Functional Requirements
| ID | Name | Priority | Description | Source | Layers |
|----|------|----------|-------------|--------|--------|
| FR-02.01 | /orders | Must | Persist rows to the database | enrichment.json | unit, integration |
"""


def _ids(reqs):
    return {r.id for r in reqs}


def test_layers_column_does_not_drop_frs():
    reqs = parse_fr_table(_4COL, split="01", spec_path="s.md")
    assert _ids(reqs) == {"FR-01.01", "FR-01.02"}


def test_body_extracted_from_correct_column_4col():
    by = {r.id: r for r in parse_fr_table(_4COL, split="01", spec_path="s.md")}
    assert by["FR-01.01"].text == "User can sign in"
    assert by["FR-01.02"].text == "Persist an order"
    # the Layers cell must never leak into the FR body
    assert "unit" not in by["FR-01.01"].text


def test_backward_compat_3col_still_parses():
    reqs = parse_fr_table(_3COL, split="01", spec_path="s.md")
    assert _ids(reqs) == {"FR-01.01"}
    assert reqs[0].text == "User can sign in"
    assert reqs[0].priority == "Must"


def test_6col_adopt_with_layers_body_is_description():
    reqs = parse_fr_table(_6COL, split="02", spec_path="s.md")
    assert _ids(reqs) == {"FR-02.01"}
    # 5-col+ adopt shape: body is the Description column (ADR-031), not Name/Layers.
    assert reqs[0].text == "Persist rows to the database"


def test_trailing_tolerance_is_linear_time_on_a_pathological_row():
    # Originally a ReDoS guard on `(?:[^|]*\|)*`. S4 removed the regex entirely --
    # the reader splits on unescaped pipes, so the backtracking class is gone by
    # construction rather than by a hardened pattern. The timing assertion is kept
    # as the standing guard that no future reader reintroduces a quadratic scan.
    import time

    row = "| FR-01.01 | body | Must |" + (" x |" * 4000)
    start = time.perf_counter()
    reqs = parse_fr_table(_HEADER + row + "\n", split="01", spec_path="s.md")
    assert time.perf_counter() - start < 1.0
    # a row this long with only-`x` trailing cells still yields the FR (not dropped)
    assert {r.id for r in reqs} == {"FR-01.01"}


def test_a_row_without_a_closing_pipe_is_kept_not_dropped():
    # BEHAVIOUR CHANGE, S4 (convergence rule C5). The old regex required a closing
    # `|` and returned [] here. Three of the five parsers already kept such a row;
    # dropping a declared requirement over a missing terminator is the same silent
    # -loss class this campaign exists to remove. Still linear, which is what the
    # original ReDoS probe was really protecting.
    import time

    row = "| FR-01.01 | body | Must |" + (" y" * 20000)   # no closing pipe
    start = time.perf_counter()
    reqs = parse_fr_table(_HEADER + row + "\n", split="01", spec_path="s.md")
    assert time.perf_counter() - start < 1.0
    assert [(r.id, r.priority) for r in reqs] == [("FR-01.01", "Must")]

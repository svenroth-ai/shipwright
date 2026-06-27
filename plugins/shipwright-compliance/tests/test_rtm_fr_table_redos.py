"""Regression for CodeQL py/redos on ``rtm._FR_TABLE_RE``.

The trailing "further columns, ignored" group was ``(?:\\s*[^|]*?\\s*\\|)*`` —
``\\s`` overlaps ``[^|]``, so a whitespace-heavy row with many ``|`` cells that
fails ``$`` backtracked exponentially. The de-ambiguated ``(?:[^|]*\\|)*`` matches
the same language in linear time. These tests pin BOTH facts: the accepted rows
still parse identically, and the pathological row resolves near-instantly.
"""

from __future__ import annotations

import time

from scripts.lib.collectors.rtm import _FR_TABLE_RE


def test_three_column_row_still_parses() -> None:
    m = _FR_TABLE_RE.match("| FR-01.01 | login | Must |")
    assert m is not None
    assert m.group(1) == "FR-01.01"
    assert m.group(2) == "login"
    assert m.group(3) == "Must"


def test_five_column_row_captures_description_and_source() -> None:
    row = "| FR-02.03 | /run | Should | Orchestrate the pipeline | spec.md |"
    m = _FR_TABLE_RE.match(row)
    assert m is not None
    assert m.group(4) == "Orchestrate the pipeline"
    assert m.group(5) == "spec.md"


def test_six_plus_column_row_matches_and_ignores_trailing() -> None:
    # Adopt specs append e.g. a Confidence column after Source — must still match.
    row = "| FR-01.01 | /run | Must | Orchestrate | enrichment.json | 0.82 |"
    m = _FR_TABLE_RE.match(row)
    assert m is not None
    assert m.group(1) == "FR-01.01"
    assert m.group(5) == "enrichment.json"  # Source still group 5; 0.82 discarded


def test_non_fr_row_rejected() -> None:
    assert _FR_TABLE_RE.match("| not-an-fr | x | Must |") is None


def test_no_catastrophic_backtracking_on_many_blank_cells() -> None:
    evil = "| FR-01.01 | x | Must |" + "   |" * 40 + "x"  # trailing 'x' fails $
    start = time.perf_counter()
    assert _FR_TABLE_RE.match(evil) is None
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"match took {elapsed:.2f}s — ReDoS regression"

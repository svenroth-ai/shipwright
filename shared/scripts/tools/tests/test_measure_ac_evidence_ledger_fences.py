"""``measure_ac_evidence_ledger.py`` — fenced-code-block handling. Split out
of ``test_measure_ac_evidence_ledger.py`` (2026-09-16, bloat gate) once the
CI Tier-3 PR-review gate's two rounds of findings (tilde fences not
recognized, then CommonMark fence-matching semantics: same character, run
length >= opener's, no info string on close) grew this corner into its own
cluster of fixtures, independent of the row/legend-exclusion mechanism the
sibling file pins.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import measure_ac_evidence_ledger as measure_mod  # noqa: E402


def test_fenced_code_block_table_example_is_not_counted() -> None:
    """A pipe-prefixed example table inside a fenced code block — the shape
    of the live ledger's own Python snippet — must not be read as a real
    row (Internal Plan Review finding 4)."""
    text = (
        "Some real rows:\n"
        "| 1 | a | `unimplemented` | note |\n\n"
        "An example, not a real row:\n"
        "```\n"
        "| 2 | b | `enforced` | note |\n"
        "```\n"
    )
    counts = measure_mod.count_statuses(text)
    assert counts["unimplemented"] == 1
    assert counts["enforced"] == 0


def test_unterminated_fence_is_reported_and_excludes_the_rest_of_the_document() -> None:
    """An odd number of ` ``` ` markers (a hand-edit mistake, not a real
    fence pair) must not be silently swallowed as a clean, lower count —
    `measure()` reports it via `unterminated_fence` (code review finding 5)."""
    text = (
        "| 1 | a | `unimplemented` | note |\n\n"
        "```\n"
        "unterminated fence — no closing marker below\n"
        "| 2 | b | `enforced` | note |\n"
    )
    result = measure_mod.measure(text)
    assert result["unterminated_fence"] is True
    assert result["status_counts"]["unimplemented"] == 1
    assert result["status_counts"]["enforced"] == 0  # inside the open fence — excluded


def test_balanced_fence_reports_no_unterminated_fence() -> None:
    result = measure_mod.measure("```\n| `enforced` |\n```\n")
    assert result["unterminated_fence"] is False


def test_tilde_fenced_code_block_table_example_is_not_counted() -> None:
    """A ``~~~`` fence is as valid as a backtick fence (CI PR-review finding)."""
    text = (
        "Some real rows:\n"
        "| 1 | a | `unimplemented` | note |\n\n"
        "An example, not a real row:\n"
        "~~~\n"
        "| 2 | b | `enforced` | note |\n"
        "~~~\n"
    )
    counts = measure_mod.count_statuses(text)
    assert counts["unimplemented"] == 1
    assert counts["enforced"] == 0


def test_mismatched_fence_markers_do_not_close_each_other() -> None:
    """A `~~~` line inside an open ``` fence is content, not a close marker —
    CommonMark closes a fence only with a matching marker."""
    text = (
        "```\n"
        "~~~\n"
        "| `enforced` |\n"
        "```\n"
        "| `unimplemented` |\n"
    )
    result = measure_mod.measure(text)
    assert result["unterminated_fence"] is False
    assert result["status_counts"]["enforced"] == 0  # inside the ``` fence
    assert result["status_counts"]["unimplemented"] == 1  # after it closed


def test_info_string_content_line_does_not_close_a_fence() -> None:
    """A closing fence carries no info string (CommonMark) — a content line
    like "```python" inside an already-open fence is a fence OPENER shape,
    not a valid close, so it must not end the fence early (CI PR-review)."""
    text = (
        "```\n"
        "example markdown showing a fence:\n"
        "```python\n"
        "| `enforced` |\n"
        "```\n"
        "| `unimplemented` |\n"
    )
    result = measure_mod.measure(text)
    assert result["unterminated_fence"] is False
    assert result["status_counts"]["enforced"] == 0  # still inside the outer fence
    assert result["status_counts"]["unimplemented"] == 1  # after it closed


def test_closing_fence_must_be_at_least_as_long_as_the_opener() -> None:
    """CommonMark: a fence closes only with a run of the SAME character at
    least as long as the opener's — a shorter run is content (CI PR-review)."""
    text = (
        "````\n"
        "| `enforced` |\n"
        "```\n"
        "| `unimplemented` |\n"
        "````\n"
        "| `no-oracle` |\n"
    )
    result = measure_mod.measure(text)
    assert result["unterminated_fence"] is False
    assert result["status_counts"]["enforced"] == 0  # ``` (3) doesn't close ```` (4)
    assert result["status_counts"]["unimplemented"] == 0  # still inside
    assert result["status_counts"]["no-oracle"] == 1  # after the real close

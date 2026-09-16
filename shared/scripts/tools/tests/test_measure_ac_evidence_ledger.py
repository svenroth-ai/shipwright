"""``measure_ac_evidence_ledger.py`` — the re-measurement script for the REQ-3
AC-evidence ledger (campaign ``req3-06-enforcement-mono``, sub-iterate
``e0-ledger-accounting``). These tests exercise the counting logic against
small synthetic fixtures, which pins the *mechanism* independent of the
real ledger's ever-changing content. The one test that runs against the
REAL committed ledger and cross-checks its live output against the
ledger's own "Re-measured" header paragraph lives in the sibling file
``test_measure_ac_evidence_ledger_real_ledger.py`` (split out 2026-09-16 to
keep this file under the project's 300-line guideline).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import measure_ac_evidence_ledger as measure_mod  # noqa: E402


def test_counts_each_canonical_status_once_per_occurrence() -> None:
    text = (
        "| 1 | a | `enforced` | note |\n"
        "| 2 | b | `enforced, tested` | note |\n"
        "| 3 | c | `enforced, untested` | note |\n"
        "| 4 | d | `enforced, partly tested` | note |\n"
        "| 5 | e | `prompt-only (mechanisable)` | note |\n"
        "| 6 | f | `prompt-only (judgement)` | note |\n"
        "| 7 | g | `unimplemented` | note |\n"
        "| 8 | h | `no-oracle` | note |\n"
    )
    counts = measure_mod.count_statuses(text)
    assert counts == {
        "enforced, partly tested": 1,
        "enforced, untested": 1,
        "enforced, tested": 1,
        "enforced": 1,
        "prompt-only (mechanisable)": 1,
        "prompt-only (judgement)": 1,
        "unimplemented": 1,
        "no-oracle": 1,
    }


def test_qualified_status_does_not_double_count_as_bare_enforced() -> None:
    """A `` `enforced, tested` `` occurrence must not also increment the bare
    `` `enforced` `` count — the longest-alternative-first / consume-on-match
    behaviour this script depends on to avoid inflating the backlog line."""
    text = "| C | central | `enforced, tested` | the only occurrence |"
    counts = measure_mod.count_statuses(text)
    assert counts["enforced, tested"] == 1
    assert counts["enforced"] == 0


def test_split_row_contributes_to_both_halves() -> None:
    """A row that splits its promise (e.g. `enforced` for the mechanism,
    `unimplemented` for a missing half) contributes to BOTH categories —
    the ledger's own documented reason row-count and criterion-count
    diverge (its End-check section states this explicitly)."""
    text = "| 6 | c | `enforced` (two of three) + `unimplemented` (the third) | note |"
    counts = measure_mod.count_statuses(text)
    assert counts["enforced"] == 1
    assert counts["unimplemented"] == 1


def test_backlog_line_excludes_enforced_and_no_oracle() -> None:
    counts = {
        "enforced, partly tested": 1, "enforced, untested": 2, "enforced, tested": 3,
        "enforced": 99, "prompt-only (mechanisable)": 4, "prompt-only (judgement)": 5,
        "unimplemented": 6, "no-oracle": 99,
    }
    backlog = {status: counts[status] for status in measure_mod.BACKLOG_STATUSES}
    assert backlog == {
        "prompt-only (mechanisable)": 4, "prompt-only (judgement)": 5,
        "enforced, untested": 2, "unimplemented": 6, "enforced, tested": 3,
    }
    line = measure_mod.format_backlog_line(backlog)
    assert line == (
        "4 prompt-only (mechanisable), 5 prompt-only (judgement), "
        "2 enforced-untested, 6 unimplemented, 3 enforced-tested"
    )


def test_main_reads_a_file_and_reports_json(tmp_path, capsys) -> None:
    ledger = tmp_path / "ledger.md"
    ledger.write_text(
        "| 1 | a | `unimplemented` | note |\n"
        "| 2 | b | `unimplemented` | note |\n",
        encoding="utf-8",
    )
    code = measure_mod.main(["--file", str(ledger), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status_counts"]["unimplemented"] == 2
    assert payload["backlog_line"]["unimplemented"] == 2


def test_main_reports_infra_error_on_missing_file(tmp_path, capsys) -> None:
    missing = tmp_path / "does-not-exist.md"
    code = measure_mod.main(["--file", str(missing), "--json"])
    assert code == 2
    err = capsys.readouterr().err
    assert "could not read" in err


def test_main_human_readable_output_shows_the_backlog_line(tmp_path, capsys) -> None:
    """The non-`--json` path — what the ledger actually tells a reader to
    run — was previously exercised only via `format_backlog_line` on a dict
    literal, never end-to-end through `main()` (external code review, glm,
    low)."""
    ledger = tmp_path / "ledger.md"
    ledger.write_text("| 1 | a | `unimplemented` | note |\n", encoding="utf-8")
    code = measure_mod.main(["--file", str(ledger)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Distribution:" in out
    assert "1 unimplemented" in out  # the backlog line, plain (no `--json`)


def test_prose_mention_of_a_status_does_not_inflate_the_count() -> None:
    """Regression test for the 2026-09-12 incident (`e3-checks-test-security`,
    PR #748): a REAL criterion table plus an explanatory paragraph that
    mentions two statuses in backticks while narrating a row split — the
    exact shape that inflated the live count past the ADR/decision-drop's
    recorded totals and produced a spec-reviewer REJECT. The paragraph is
    not a table row, so it must not move the count at all."""
    criterion_rows = (
        "| 1 | a | `unimplemented` | note |\n"
        "| 2 | b | `prompt-only (mechanisable)` | note |\n"
    )
    explanatory_prose = (
        "\nSplitting #6 into #6 (`enforced, tested`) / #6b (`prompt-only "
        "(mechanisable)`, deferred) because the original bare `enforced, "
        "tested` tag over-claimed against the check's own weak-oracle "
        "caveat.\n"
    )
    counts_without_prose = measure_mod.count_statuses(criterion_rows)
    counts_with_prose = measure_mod.count_statuses(criterion_rows + explanatory_prose)
    assert counts_with_prose == counts_without_prose
    assert counts_with_prose["unimplemented"] == 1
    assert counts_with_prose["prompt-only (mechanisable)"] == 1
    assert counts_with_prose["enforced, tested"] == 0


def test_legend_and_summary_tables_are_excluded_by_their_status_first_header() -> None:
    """A table block whose header row starts with `| Status |` — the shape
    of both the vocabulary legend and the historical end-check summary
    table — must not contribute to the count, even though it IS a table
    row and even though it mentions every canonical status. A real
    criterion table's header never starts this way (`Status` is a later
    column: `| # | Criterion | Status | ... |`), so this rule does not
    touch real rows."""
    criterion_rows = (
        "| # | Criterion | Status | Evidence |\n"
        "|---|---|---|---|\n"
        "| 1 | a | `unimplemented` | note |\n"
    )
    legend = (
        "| Status | What it means | Who fixes it | How |\n"
        "|---|---|---|---|\n"
        "| `enforced` | ... | — | nothing |\n"
        "| `unimplemented` | ... | team | build it |\n"
    )
    summary = (
        "| Status | Rows |\n"
        "|---|---|\n"
        "| `enforced` | 0 |\n"
        "| `unimplemented` | 5 |\n"
    )
    counts = measure_mod.count_statuses(criterion_rows + "\n" + legend + "\n" + summary)
    assert counts["unimplemented"] == 1
    assert counts["enforced"] == 0


def test_fixture_naming_every_status_in_prose_and_legend_counts_rows_only() -> None:
    """The regression fixture the fix's own spec calls for: prose AND the
    legend each mention every canonical status in backticks, alongside a
    real criterion table that uses each status exactly once. The count
    must equal the row count for every status — not row count + legend +
    prose — proving both exclusions (non-table-row, `Status`-first table)
    hold simultaneously for every status, not just the ones used above."""
    rows = "\n".join(
        f"| {i} | c{i} | `{status}` | note |"
        for i, status in enumerate(measure_mod.CANONICAL_STATUSES, start=1)
    )
    legend = "\n".join(f"| `{status}` | meaning | who | how |" for status in measure_mod.CANONICAL_STATUSES)
    legend = "| Status | What it means | Who fixes it | How |\n|---|---|---|---|\n" + legend
    prose = " ".join(f"Also mentioned in prose: `{status}`." for status in measure_mod.CANONICAL_STATUSES)
    text = rows + "\n\n" + legend + "\n\n" + prose + "\n"
    counts = measure_mod.count_statuses(text)
    assert counts == {status: 1 for status in measure_mod.CANONICAL_STATUSES}


def test_excluded_tables_are_reported_for_audit() -> None:
    """`measure()` must name which blocks it dropped, not just drop them
    silently (Internal Plan Review finding 2, 2026-09-16) — a reader has to
    be able to verify only the legend/summary shape was excluded, not a
    future criterion table that happens to share the `Status`-first shape."""
    criterion_rows = "| 1 | a | `unimplemented` | note |\n"
    legend = "| Status | What it means |\n|---|---|\n| `unimplemented` | ... |\n"
    text = criterion_rows + "\n" + legend
    result = measure_mod.measure(text)
    assert result["excluded_tables"] == [{"line": 3, "header": "| Status | What it means |"}]


def test_legend_glued_to_a_preceding_table_with_no_blank_line_is_not_excluded() -> None:
    """The exclusion is block-scoped: a blank line above the legend is what
    keeps it a separate block from a preceding criterion table. Documents
    the real (non-excluded) behavior when that separator is missing — a
    future edit that glues the two together silently stops excluding the
    legend, and this test is the place a reader learns that from a passing
    assertion rather than from a failure message (code review finding 3)."""
    criterion_row = "| 1 | a | `unimplemented` | note |\n"
    legend_no_blank_line = "| Status | What it means |\n|---|---|\n| `unimplemented` | ... |\n"
    glued = criterion_row + legend_no_blank_line  # no blank line between them
    counts = measure_mod.count_statuses(glued)
    # Merged into one block; its header is the criterion row, not "Status",
    # so nothing is excluded and the legend's own mention now counts too.
    assert counts["unimplemented"] == 2


def test_status_header_match_is_structural_not_a_literal_prefix() -> None:
    """The exclusion rule reads the header's first CELL, not a literal
    string prefix — a whitespace variant (`|Status|` or `| Status  |`) must
    still be recognised, and must not depend on a second header column
    being present at all (Internal Plan Review finding 2)."""
    no_space = "|Status|Rows|\n|---|---|\n|`unimplemented`|5|\n"
    extra_space = "|  Status  | Rows |\n|---|---|\n| `unimplemented` | 5 |\n"
    single_cell = "|Status|\n|---|\n| `unimplemented` |\n"
    assert measure_mod.count_statuses(no_space)["unimplemented"] == 0
    assert measure_mod.count_statuses(extra_space)["unimplemented"] == 0
    assert measure_mod.count_statuses(single_cell)["unimplemented"] == 0


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

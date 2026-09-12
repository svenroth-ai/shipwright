"""``measure_ac_evidence_ledger.py`` — the re-measurement script for the REQ-3
AC-evidence ledger (campaign ``req3-06-enforcement-mono``, sub-iterate
``e0-ledger-accounting``). Most tests exercise the counting logic against
small synthetic fixtures, which pins the *mechanism* independent of the
real ledger's ever-changing content. One test (external code review,
2026-09-11, both providers, medium) runs against the REAL committed ledger
and cross-checks its live output against the ledger's own "Re-measured"
header paragraph — so a future edit that silently drifts the two apart
(a walk changes rows without re-running the script, or someone hand-edits
the header) fails HERE instead of being caught nowhere at all.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import measure_ac_evidence_ledger as measure_mod  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]  # tests -> tools -> scripts -> shared -> repo
_REAL_LEDGER = _REPO_ROOT / measure_mod.DEFAULT_LEDGER_RELPATH

# Matches the ledger's own "Re-measured <date>" header paragraphs, e.g.
# "**47** prompt-only/mechanisable · **19** prompt-only/judgement · **16**
# enforced-untested · **36** unimplemented · **50** enforced-tested" —
# deliberately NOT backtick-quoted there (see that paragraph's own note) so
# this regex, unlike the script's own counter, must match the plain words.
# The ledger keeps every superseded paragraph for its own history (each
# says so explicitly), so this shape can appear more than once in the
# document; the paragraphs are appended chronologically, so the LAST match
# is the current one — callers must not use plain `.search()` here.
_HEADER_LINE_RE = re.compile(
    r"\*\*(\d+)\*\*\s*prompt-only/mechanisable\s*.\s*"
    r"\*\*(\d+)\*\*\s*prompt-only/judgement\s*.\s*"
    r"\*\*(\d+)\*\*\s*enforced-untested\s*.\s*"
    r"\*\*(\d+)\*\*\s*unimplemented\s*.\s*"
    r"\*\*(\d+)\*\*\s*enforced-tested",
)


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


def test_legend_and_summary_style_text_inflates_by_a_known_fixed_amount() -> None:
    """Pins the exact, documented imprecision (external code review, glm,
    medium) rather than merely asserting it in prose: a legend-shaped
    sentence and a distribution-table-shaped sentence each name every
    canonical status once in backticks, so a mini-ledger built from N real
    criterion rows PLUS one legend-shaped block PLUS one summary-shaped
    block must count exactly N + 2 for every status both blocks name (and
    N + 1 for `enforced, tested` / `enforced, partly tested`, which the
    legend never mentions — see the module docstring)."""
    criterion_rows = (
        "| 1 | a | `unimplemented` | note |\n"
        "| 2 | b | `prompt-only (mechanisable)` | note |\n"
    )
    legend_shaped = (
        "| `enforced` | ... |\n"
        "| `enforced, untested` | ... |\n"
        "| `prompt-only (mechanisable)` | ... |\n"
        "| `prompt-only (judgement)` | ... |\n"
        "| `unimplemented` | ... |\n"
        "| `no-oracle` | ... |\n"
    )
    summary_shaped = (
        "| `enforced` | 0 |\n"
        "| `prompt-only (mechanisable)` | 1 |\n"
        "| `enforced, tested` | 0 |\n"
        "| `unimplemented` | 1 |\n"
        "| `prompt-only (judgement)` | 0 |\n"
        "| `enforced, untested` | 0 |\n"
        "| `no-oracle` | 0 |\n"
        "| `enforced, partly tested` | 0 |\n"
    )
    counts = measure_mod.count_statuses(criterion_rows + legend_shaped + summary_shaped)
    # named by both blocks: +2 over the real row count
    assert counts["unimplemented"] == 1 + 2
    assert counts["prompt-only (mechanisable)"] == 1 + 2
    assert counts["enforced"] == 0 + 2
    assert counts["prompt-only (judgement)"] == 0 + 2
    assert counts["enforced, untested"] == 0 + 2
    assert counts["no-oracle"] == 0 + 2
    # named only by the summary block: +1 over the real row count
    assert counts["enforced, tested"] == 0 + 1
    assert counts["enforced, partly tested"] == 0 + 1


def test_real_ledger_header_matches_the_live_measurement() -> None:
    """Guards against exactly the drift this script exists to catch: a future
    walk changes rows (or someone hand-edits the header) and the two go out of
    sync. Skipped, not failed, if the ledger has moved/been renamed — this
    test's job is "catch drift while the file exists", not "pin the file's
    location forever"."""
    if not _REAL_LEDGER.is_file():
        pytest.skip(f"real ledger not found at {_REAL_LEDGER} (moved/renamed?)")

    text = _REAL_LEDGER.read_text(encoding="utf-8")
    header_matches = list(_HEADER_LINE_RE.finditer(text))
    assert header_matches, (
        "the ledger's 'Re-measured' header paragraph was not found in the "
        "expected shape — either it was reworded (update _HEADER_LINE_RE to "
        "match) or removed (put it back, per the e0-ledger-accounting spec's "
        "AC 'the re-measured counts are written into the ledger header')"
    )
    # Superseded paragraphs are kept for history and share this exact shape
    # (see the regex's own comment above) — the current one is whichever
    # was appended last, i.e. the last match in the document.
    header_match = header_matches[-1]
    header_counts = {
        "prompt-only (mechanisable)": int(header_match.group(1)),
        "prompt-only (judgement)": int(header_match.group(2)),
        "enforced, untested": int(header_match.group(3)),
        "unimplemented": int(header_match.group(4)),
        "enforced, tested": int(header_match.group(5)),
    }
    live_counts = measure_mod.measure(text)["backlog_line"]
    assert header_counts == live_counts, (
        f"the ledger header claims {header_counts} but the live measurement "
        f"is {live_counts} — re-run `uv run "
        f"shared/scripts/tools/measure_ac_evidence_ledger.py` and update the "
        f"header paragraph to match"
    )

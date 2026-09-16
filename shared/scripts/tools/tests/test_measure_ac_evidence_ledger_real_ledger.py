"""``measure_ac_evidence_ledger.py`` — the drift guard against the REAL
committed ledger (campaign ``req3-06-enforcement-mono``). Split out of
``test_measure_ac_evidence_ledger.py`` (which pins the counting *mechanism*
against small synthetic fixtures) once this file's own docstring's
long-standing description of "one test runs against the real ledger" made
the split boundary obvious — this is that one test, plus the fixture it
needs, both moved as a unit to keep the fixture-tests file under the
project's 300-line guideline (2026-09-16, bloat gate).

Cross-checks the script's live output against the ledger's own
"Re-measured" header paragraph, so a future edit that silently drifts the
two apart (a walk changes rows without re-running the script, or someone
hand-edits the header) fails HERE instead of being caught nowhere at all.
"""

from __future__ import annotations

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
    measured = measure_mod.measure(text)
    live_counts = measured["backlog_line"]
    assert header_counts == live_counts, (
        f"the ledger header claims {header_counts} but the live measurement "
        f"is {live_counts}. FIRST check WHY it moved before touching the "
        f"header: if the diff added/changed criterion ROWS, re-run `uv run "
        f"shared/scripts/tools/measure_ac_evidence_ledger.py` and update the "
        f"header paragraph to match. If the diff changed DOCUMENT STRUCTURE "
        f"instead (a new table, a lost blank line above the legend, a "
        f"backtick-quoted status added to prose or to a non-status table "
        f"cell), fix the structure or the counter — do NOT blindly overwrite "
        f"the header with the new number; that is the exact mistake the "
        f"2026-09-12 incident made (iterate-2026-09-16-ac-ledger-status-cell-counting)."
    )
    # The exclusion rule must drop exactly the legend and the historical
    # summary table — nothing more, nothing less (Internal Plan Review
    # finding 2: a silent third exclusion is an unbounded under-count).
    assert len(measured["excluded_tables"]) == 2, (
        f"expected exactly 2 excluded tables (the legend + the historical "
        f"summary), got {measured['excluded_tables']} — a new `Status`-first "
        f"table appeared (verify it is not a real criterion table being "
        f"silently dropped) or one of the two known tables lost its header "
        f"shape"
    )

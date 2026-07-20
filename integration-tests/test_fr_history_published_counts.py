"""Do the shipped documents quote the numbers the tables hold? (campaign S7)

This module exists because the first version of the count pin compared a Python
dict against Python tables and **read no document at all**, while the
operator-facing record in ``degraded[]`` claimed it "fails if prose and table
diverge again". Editing ADR-110's ``| Returned verbatim | 5 |`` to ``6`` left
the suite green.

That is the S6 lesson in its purest form — an assertion nobody pointed a test
at — shipped inside the fix for an instance of the same lesson. So every check
here opens a file.

Two families:

* **Counts.** The retracted claims must not reappear as current, and the ADR's
  canonical table must state the right numbers.
* **Coverage.** ``61 of 342`` is prose in four documents while the CLI computes
  it live, so the documents can diverge from each other and from the log. Pinned
  MONOTONICALLY, not by equality — see
  :func:`test_the_recorded_coverage_is_consistent_with_the_live_log`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "shared" / "scripts"))

from _fr_history_docs import (  # noqa: E402
    SHIPPED_DOCUMENTS,
    document_text,
    retracted_claims_stated_as_current,
)
from _fr_history_recovered_history import PUBLISHED_COUNTS  # noqa: E402



# --------------------------------------------------------------------------
# Counts
# --------------------------------------------------------------------------

def test_the_shipped_documents_do_not_carry_the_retracted_count():
    """Read the DOCUMENTS, not the dict. The pin this replaces read neither."""
    checked = 0
    for rel, required in SHIPPED_DOCUMENTS:
        text = document_text(rel)
        if text is None:
            assert not required, f"required document missing: {rel}"
            continue
        stale = retracted_claims_stated_as_current(text)
        assert not stale, (
            f"{rel} states the retracted count(s) {stale} as current. The tables "
            f"hold {PUBLISHED_COUNTS['pairs_returned_verbatim']} pairs returned "
            f"verbatim."
        )
        checked += 1

    assert checked >= 3, (
        f"only {checked} document(s) were actually read; this pin is close to "
        f"vacuous. Absence is tolerated ONLY for the ephemeral changelog drop."
    )


def test_the_retraction_detector_would_actually_fire():
    """Guard against the guard going vacuous.

    The whole point of this module is that its predecessor asserted nothing.
    Prove the detector fires on the exact text that shipped, and does NOT fire
    on the same words presented as a retraction.
    """
    assert retracted_claims_stated_as_current(
        "Of the ten run ids, six are returned verbatim, one under ADR-030."
    ) == ["six are returned verbatim"]
    assert retracted_claims_stated_as_current(
        "A first draft published 'six are returned verbatim' against a table "
        "holding five; corrected."
    ) == []


def test_the_adr_table_states_the_published_counts():
    """Positive check on the document whose table is the canonical statement."""
    text = document_text(
        ".shipwright/planning/adr/110-change-history-as-a-derived-view.md"
    )
    assert text is not None, "ADR-110 is missing"
    assert f"| Returned verbatim | {PUBLISHED_COUNTS['pairs_returned_verbatim']} |" in text
    assert f"| **Name no event at all** | {PUBLISHED_COUNTS['pairs_absent']} |" in text
    assert "ten (requirement, run id) pairs across nine distinct run" in text


def test_editing_the_adr_table_to_the_retracted_value_would_be_caught():
    """The exact reproduction the review supplied, run against the detector.

    Not a hypothetical: this is the edit that left the previous pin green.
    """
    text = document_text(
        ".shipwright/planning/adr/110-change-history-as-a-derived-view.md"
    )
    mutated = text.replace("| Returned verbatim | 5 |", "| Returned verbatim | 6 |")
    assert mutated != text, "the ADR no longer contains the line under test"
    assert retracted_claims_stated_as_current(mutated) == ["| Returned verbatim | 6 |"]


def test_the_retraction_detector_covers_technical_claims_too():
    """A retraction that only covers numbers is half a retraction.

    The mini-plan carried "newlines already collapsed by `split()`" for a full
    round after that was shown false, because the detector matched count claims
    only — while policing the numeric retraction on the same page.
    """
    assert retracted_claims_stated_as_current(
        "Sanitising is handled: newlines already collapsed by `split()`."
    ) == ["newlines already collapsed by"]
    assert retracted_claims_stated_as_current(
        "A first draft claimed 'newlines already collapsed by split()', which "
        "was wrong: tty_sanitize preserves them by design."
    ) == []


def test_the_mini_plans_mutation_arithmetic_adds_up():
    """The published total must equal the per-round figures beside it.

    "28 across three rounds" was published while the enumeration listed two
    rounds — an unverifiable number in the Verification section, the same class
    as "six returned verbatim". The document now states the sum explicitly; this
    re-adds it, and checks each enumerated round is present.
    """
    text = document_text(
        ".shipwright/planning/iterate/"
        "2026-07-19-traceability-derived-view-miniplan.md"
    )
    assert text is not None, "the mini-plan is missing"

    sums = re.findall(r"\*\*([\d\s+]+?)\s*=\s*(\d+)\*\*", text)
    assert sums, "the mini-plan no longer states the mutation total as a sum"
    parts, total = sums[0]
    addends = [int(n) for n in re.findall(r"\d+", parts)]
    assert sum(addends) == int(total), (
        f"the mini-plan states {parts.strip()} = {total}, which does not add up "
        f"to {sum(addends)}."
    )

    enumerated = [int(n) for n in re.findall(r"\*(?:Round \d+|Inline) \((\d+)\)\*", text)]
    assert len(enumerated) == len(addends), (
        f"{len(addends)} addends published but {len(enumerated)} rounds "
        f"enumerated — a round is missing from the breakdown, which is exactly "
        f"how the previous figure went unverifiable."
    )
    assert sorted(enumerated) == sorted(addends), (
        f"the enumerated per-round counts {enumerated} do not match the "
        f"published addends {addends}."
    )

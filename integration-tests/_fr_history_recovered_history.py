"""The change history S6 deleted from the catalog, recovered from git (S7).

Data only — the assertions live in
``test_fr_change_history_recovers_compacted_history.py``. Split out so the test
module stays under the size limit, and because this IS the evidence: it is worth
reading on its own without the test scaffolding around it.

Provenance
----------
Every run id below was read from the pre-S6 catalog at commit ``5eef5076``::

    git show 5eef5076:.shipwright/planning/01-adopted/spec.md | grep -n "Refined by"

NOT from the S6 ADR's summary of what it removed, and not from memory. The test
module re-checks that provenance rather than trusting this docstring.

Counting
--------
Three different quantities are involved and they do NOT coincide. Every one is
recorded here so a reader never has to reconcile them by hand:

1. **``Refined by`` blocks** — FR-01.11 six, FR-01.14 five. This is the number
   ADR-109 and the S7 spec quote.
2. **Distinct run ids named** — five each. Lower than the block count for two
   independent reasons, one per requirement (see :data:`BLOCK_RECONCILIATION`).
3. **(requirement, run id) pairs** — ten across **nine** distinct run ids,
   because ``iterate-2026-05-16-backfill-historical-frs`` is named by both
   requirements and is absent from the log for both.

Quantity 1 vs 2 is the reconciliation an earlier draft left unstated, which read
as a sixth run id having been dropped from the recovery. It was not: FR-01.11's
sixth block attributes to ``BP-1``, a baseline-plan identifier that is not a run
at all. Quantity 2 vs 3 is how that same draft published "six returned verbatim"
against a table holding five, by subtracting distinct ids from a pair total.

:data:`PUBLISHED_COUNTS` pins all of it against the tables AND against the
shipped documents.
"""

from __future__ import annotations

#: The pre-S6 commit the expectations were read from.
PRE_S6_COMMIT = "5eef5076"

#: The requirements whose removed blocks are checked.
FRS = ("FR-01.11", "FR-01.14")

#: Run ids the removed blocks named, that the query returns VERBATIM.
RECOVERED_EXACT = {
    "FR-01.11": (
        "iterate-2026-05-16-spec-impact-gate",
        "iterate-2026-07-14-f0-parallel-suite",
        "iterate-2026-07-18-fr-authoring-rules",
    ),
    "FR-01.14": (
        "iterate-2026-07-18-outbox-newline-corruption",
        "iterate-2026-05-21-security-artifact-producer",
    ),
}

#: Run ids whose CHANGE is in the log, under the ``ADR-NNN`` id the event log
#: used before run-id-shaped ``adr_id`` values began on 2026-05-16. Nothing is
#: lost here — the label differs, the record does not. Value is
#: ``(adr_label, marker that must appear in the event's own summary)``, so the
#: mapping is asserted against the data rather than taken on trust.
RECOVERED_UNDER_ADR_ID = {
    "FR-01.11": {
        "iterate-20260505-plugin-hook-registration": (
            "ADR-030",
            "plugin-hook-registration",
        ),
    },
    "FR-01.14": {},
}

#: Run ids that name NO event in the log, for any requirement. The work happened
#: — each maps to the commit that proves it — but it was never recorded against
#: the requirement, so the event log cannot answer for it. This is the measured
#: gap in campaign decision D4's claim.
NOT_IN_EVENT_LOG = {
    "FR-01.11": {
        "iterate-2026-05-16-backfill-historical-frs": "805d268a",
    },
    "FR-01.14": {
        "iterate-2026-05-16-backfill-historical-frs": "805d268a",
        "iterate-2026-05-19-github-triage-importer": "ff51a8cc",
        "iterate-2026-05-20-triage-launch-surface": "7b67acf6",
    },
}

#: Why each requirement's ``Refined by`` block count exceeds the number of run
#: ids recovered from it. Verified against the pre-S6 file, not against an ADR.
#:
#: ``blocks``
#:     ``Refined by`` occurrences inside that requirement's section.
#: ``run_ids``
#:     Distinct run ids the section names, from ANY attribution marker.
#: ``reason``
#:     What accounts for the difference.
BLOCK_RECONCILIATION = {
    "FR-01.11": {
        "blocks": 6,
        "run_ids": 5,
        "reason": (
            "the third block reads 'Refined by BP-1' — a baseline-plan "
            "identifier, not a run id, so it names no run to recover"
        ),
    },
    "FR-01.14": {
        "blocks": 5,
        "run_ids": 5,
        "reason": (
            "one 'Refined by' is an INLINE cross-reference to a run id another "
            "block already owns (4 distinct from 'Refined by'), and a separate "
            "'Backfilled by' marker names the fifth"
        ),
    },
}

#: Attributions that name something other than a run. Recorded rather than
#: silently skipped: an unexplained gap between "six blocks" and "five run ids"
#: reads as a run id having been dropped from the recovery.
ATTRIBUTIONS_NAMING_NO_RUN_ID = {"FR-01.11": ("BP-1",), "FR-01.14": ()}

#: Coverage of this tree's event log **as of this change**, quoted as prose in
#: ADR-110, the mini-plan, the decision log and the shipped changelog drop. The
#: CLI computes it live, so the documents can silently diverge from the log and
#: from each other.
#:
#: Pinned MONOTONICALLY, not by equality. The log is append-only, so both
#: numbers only grow: an equality pin would turn the next unrelated iterate that
#: links an FR red, which is a gate punishing correct behaviour. What must hold
#: is that the documents agree with each other, that the recorded snapshot is
#: not above the live log (which would mean it was never measured), and that the
#: qualitative claim the prose makes — a MINORITY of changes carry a link — is
#: still true.
COVERAGE_FR_LINKED_EVENTS = 61
COVERAGE_WORK_EVENTS = 342
#: Second published measurement over the same denominator: ADR-110 cites it as
#: the reason no event-schema field was added (the weakness is missing DATA, not
#: a missing field). It rots exactly like the coverage figure, and did — it was
#: published as "71 of 341" and survived the first correction because nothing
#: read it.
COMMIT_POPULATED_EVENTS = 71
#: The run whose finalization event is the last one included in the figures
#: above. Recorded so "as of" is checkable rather than implied.
COVERAGE_AS_OF_RUN = "iterate-2026-07-19-traceability-derived-view"

#: The counts published in ADR-110, the decision-log entry, the commit message,
#: the changelog drop and the PR body. Kept as data so operator-facing prose and
#: these tables cannot drift apart; pinned against BOTH by
#: ``test_the_published_counts_match_the_tables`` (arithmetic) and
#: ``test_the_shipped_documents_do_not_carry_the_retracted_count`` (the
#: documents). A stale name here would be the anti-dead-pointer machinery
#: carrying a dead pointer of its own.
PUBLISHED_COUNTS = {
    "pairs_total": 10,
    "distinct_run_ids": 9,
    "pairs_returned_verbatim": 5,
    "pairs_under_adr_label": 1,
    "pairs_absent": 4,
    "distinct_run_ids_absent": 3,
}

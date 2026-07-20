"""Does the event log actually carry the history S6 deleted from the catalog?

Campaign ``2026-07-18-requirements-catalog``, S7. Decision D4 removed the
``Refined by <run_id>`` prose blocks from the requirements catalog on the stated
grounds that the same information "already exists in commits, changelog, and
``events.jsonl``". S6 executed the removal. This module is where that claim is
checked rather than repeated.

**It does not hold for the event log alone.** Measured, not assumed. The removed
blocks named **ten (requirement, run id) pairs across nine distinct run ids** —
``iterate-2026-05-16-backfill-historical-frs`` was named by both requirements.
Of those ten pairs, **five** are returned by the query verbatim, **one** is
present under its pre-run-id ``ADR-NNN`` label, and **four are absent** — those
four being **three distinct run ids**, since the backfill run is absent for both
requirements. The three survive only in commit messages and planning documents —
which D4 also named, so the disjunction survives, but the event log is not the
complete index D4 implied it was.

The pair-count and the distinct-id count are different numbers and are stated
separately on purpose: an earlier draft of this module's own summary collapsed
them and reported "six returned verbatim", which is arithmetic on a set that was
never counted. :func:`test_the_published_counts_match_the_tables` pins both.

That gap is pinned here on purpose. The alternative — softening the claim to fit
the measurement — is the failure this campaign was called to remove.

Provenance of the expectations
------------------------------
The recovered tables live in ``_fr_history_recovered_history.py``, and
``test_fr_history_recovery_provenance.py`` proves the recovery is COMPLETE
(set equality per requirement section) and that the shipped documents quote
the counts the tables hold. Every run id
in them was read from the pre-S6 catalog at commit ``5eef5076``
(``git show 5eef5076:.shipwright/planning/01-adopted/spec.md``), NOT from the S6
ADR's summary of what it removed and not from memory. Regenerate with::

    git show 5eef5076:.shipwright/planning/01-adopted/spec.md | grep -n "Refined by"

If a later change backfills the missing events, this test fails — correctly. The
audit record would genuinely have changed, and that must be a deliberate edit
here, not a silent re-green.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "shared" / "scripts"))

from lib.fr_change_history import change_history_for_fr  # noqa: E402

from _fr_history_recovered_history import (  # noqa: E402
    FRS as _FRS,
    NOT_IN_EVENT_LOG,
    PRE_S6_COMMIT,
    PUBLISHED_COUNTS,
    RECOVERED_EXACT,
    RECOVERED_UNDER_ADR_ID,
)


def _labels(fr_id: str) -> list[str]:
    return [c.label for c in change_history_for_fr(_REPO, fr_id).changes]


@pytest.mark.parametrize("fr_id", _FRS)
def test_every_exactly_recovered_run_id_is_returned_by_the_query(fr_id):
    """The part of D4's claim that DOES hold, stated as a hard assertion."""
    returned = set(_labels(fr_id))
    missing = [r for r in RECOVERED_EXACT[fr_id] if r not in returned]
    assert not missing, (
        f"{fr_id}: run id(s) named by a removed 'Refined by' block are no longer "
        f"returned by the event-log query: {missing}. The catalog no longer "
        f"carries them either, so this is information loss, not relocation."
    )


@pytest.mark.parametrize("fr_id", _FRS)
def test_pre_run_id_changes_are_present_under_their_adr_label(fr_id):
    """A change recorded before run-id ids is still findable, under ``ADR-NNN``.

    Asserts the correspondence rather than assuming it: the ADR-labelled event
    must both name the requirement AND describe the same work the removed block
    attributed to the run id.
    """
    history = change_history_for_fr(_REPO, fr_id)
    for run_id, (adr_label, description_marker) in RECOVERED_UNDER_ADR_ID[fr_id].items():
        matching = [c for c in history.changes if c.label == adr_label]
        assert matching, (
            f"{fr_id}: removed block named {run_id!r}; the query was expected to "
            f"carry that change under {adr_label!r} and returned no such event."
        )
        blob = " ".join(c.summary for c in matching).lower()
        assert description_marker in blob, (
            f"{fr_id}: {adr_label!r} is returned, but nothing in its summary "
            f"mentions {description_marker!r}, so the claim that it IS the "
            f"{run_id!r} work is unsupported. Re-derive the mapping."
        )


@pytest.mark.parametrize("fr_id", _FRS)
def test_the_measured_gap_in_d4s_claim_stays_visible(fr_id):
    """These run ids are absent from the event log. Pinned so it cannot drift.

    Fails in BOTH directions on purpose. If one of these appears, D4's claim got
    truer and the record here is stale. If a run id currently returned stops
    being returned, the gap grew. Either way a human decides, rather than a
    suite re-greening around a changed audit trail.
    """
    returned = set(_labels(fr_id))
    unexpectedly_present = [r for r in NOT_IN_EVENT_LOG[fr_id] if r in returned]
    assert not unexpectedly_present, (
        f"{fr_id}: {unexpectedly_present} now HAS an event, but this module "
        f"records it as absent. That is good news — update NOT_IN_EVENT_LOG "
        f"(and the S7 ADR's finding) to match."
    )


@pytest.mark.parametrize("fr_id", _FRS)
def test_the_absent_run_ids_did_real_work_that_was_never_recorded(fr_id):
    """The gap is missing *records*, not imagined iterates.

    Each absent run id has a commit. That is what makes this a traceability gap
    rather than a stale reference: the change shipped, and the event log simply
    never linked it to the requirement.
    """
    for run_id, commit in NOT_IN_EVENT_LOG[fr_id].items():
        proc = subprocess.run(
            ["git", "cat-file", "-t", commit],
            cwd=_REPO, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            pytest.skip(f"commit {commit} unreachable in this checkout (shallow clone?)")
        assert proc.stdout.strip() == "commit", (
            f"{run_id}: {commit} is recorded as the commit proving this work "
            f"happened, but it is not a commit object."
        )


def test_the_published_counts_match_the_tables():
    """The numbers quoted in prose are the numbers in the tables.

    Every count above appears in shipped, operator-facing text. A first draft
    published "six returned verbatim" — derived by subtracting the *distinct*
    absent ids from the *pair* total, two different denominators. The suite was
    green throughout, because nothing pointed at the arithmetic. This does.
    """
    exact = {(fr, r) for fr in _FRS for r in RECOVERED_EXACT[fr]}
    adr = {(fr, r) for fr in _FRS for r in RECOVERED_UNDER_ADR_ID[fr]}
    absent = {(fr, r) for fr in _FRS for r in NOT_IN_EVENT_LOG[fr]}
    every = exact | adr | absent

    actual = {
        "pairs_total": len(every),
        "distinct_run_ids": len({r for _, r in every}),
        "pairs_returned_verbatim": len(exact),
        "pairs_under_adr_label": len(adr),
        "pairs_absent": len(absent),
        "distinct_run_ids_absent": len({r for _, r in absent}),
    }
    assert actual == PUBLISHED_COUNTS, (
        f"the published counts no longer describe the tables: {actual}. Update "
        f"ADR-110, the decision-log entry and this module's docstring together, "
        f"or the operator-facing record becomes fiction."
    )
    assert (
        actual["pairs_returned_verbatim"]
        + actual["pairs_under_adr_label"]
        + actual["pairs_absent"]
        == actual["pairs_total"]
    ), "the three outcome sets do not partition the recovered pairs"


def test_the_recovery_source_is_the_pre_s6_catalog_not_a_summary_of_it():
    """The expectations above must be re-derivable from git, not from prose.

    Guards the method, not the data: if ``PRE_S6_COMMIT`` stops resolving, or
    stops containing the removed blocks, then the provenance claim in this
    module's docstring is no longer checkable and the numbers become folklore.
    """
    proc = subprocess.run(
        ["git", "show", f"{PRE_S6_COMMIT}:.shipwright/planning/01-adopted/spec.md"],
        cwd=_REPO, capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        pytest.skip(f"{PRE_S6_COMMIT} unreachable in this checkout (shallow clone?)")

    blocks = [ln for ln in proc.stdout.splitlines() if "Refined by" in ln]
    assert len(blocks) >= 20, (
        f"expected the pre-S6 catalog at {PRE_S6_COMMIT} to still carry its "
        f"'Refined by' blocks; found {len(blocks)}."
    )
    every_expected = {
        run_id
        for table in (RECOVERED_EXACT, RECOVERED_UNDER_ADR_ID, NOT_IN_EVENT_LOG)
        for fr in _FRS
        for run_id in table[fr]
    }
    absent = [r for r in sorted(every_expected) if r not in proc.stdout]
    assert not absent, (
        f"run id(s) recorded here as recovered from {PRE_S6_COMMIT} do not "
        f"appear in that file: {absent}. The expectations were not read from "
        f"the source they claim."
    )

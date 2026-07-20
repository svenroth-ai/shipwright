"""The live measurements this run publishes as prose (campaign S7).

``61 of 342`` (requirement-linked changes) and ``71 of 342`` (changes carrying a
commit hash — ADR-110's stated reason for adding no schema field). The CLI
recomputes both on every run; the documents do not, so they can diverge from the
log and from each other. The second one DID: it shipped as "71 of 341" and
survived a full correction round untouched, because nothing read it.

**Pinned monotonically, never by equality.** An append-only log only grows, and
every iterate's F5b appends a ``work_completed`` event — so an equality pin is a
dated bomb that reddens the next unrelated change. A first version of the
commit-population check was written exactly that way, ten lines below a
docstring explaining why not to. What is asserted instead: the snapshot is never
above the live log, and the qualitative claim each figure supports (a *minority*)
still holds.

Counts and cross-references live in ``test_fr_history_published_counts.py`` and
``test_fr_history_cross_references.py``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "shared" / "scripts"))

from _fr_history_docs import (  # noqa: E402
    SHIPPED_DOCUMENTS,
    SUPERSEDED_MARKERS as _SUPERSEDED_MARKERS,
    document_text,
)
from _fr_history_recovered_history import (  # noqa: E402
    COMMIT_POPULATED_EVENTS,
    COVERAGE_AS_OF_RUN,
    COVERAGE_FR_LINKED_EVENTS,
    COVERAGE_WORK_EVENTS,
)

from lib._fr_history_events import read_work_events  # noqa: E402
from lib.fr_change_history import (  # noqa: E402
    change_history_for_fr,
    coverage_summary,
)


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------

def test_every_measurement_quoted_over_the_event_log_is_current():
    """Two live measurements are published as prose over the same denominator.

    ``61 of 342`` (requirement-linked changes) and ``71 of 342`` (changes
    carrying a commit hash — ADR-110's stated reason for adding no schema
    field). Both rot as the log grows, and the second DID: it shipped as
    "71 of 341" and survived the first correction untouched, because nothing
    read it. So the check matches *any* ``N of M`` phrase rather than one known
    string — an unrecognised pair is a measurement nobody pinned.
    """
    permitted = {
        f"{COVERAGE_FR_LINKED_EVENTS} of {COVERAGE_WORK_EVENTS}",
        f"{COMMIT_POPULATED_EVENTS} of {COVERAGE_WORK_EVENTS}",
    }
    pair_re = re.compile(r"\b\d{2,4} of \d{2,4}\b")

    checked = 0
    for rel, required in SHIPPED_DOCUMENTS:
        text = document_text(rel)
        if text is None:
            assert not required, f"required document missing: {rel}"
            continue

        unknown: set[str] = set()
        found_any = False
        for match in pair_re.finditer(text):
            found_any = True
            pair = match.group(0)
            if pair in permitted:
                continue
            # A figure quoted as a SUPERSEDED value — this run's own event
            # records 60 of 341, deliberately unamended because the log is
            # append-only — is the subject matter, not a stale claim. Same
            # allowance the retraction detector makes, and without it the
            # record of why the divergence exists would trip the check on it.
            window = text[max(0, match.start() - 300):match.end() + 300].lower()
            if any(m in window for m in _SUPERSEDED_MARKERS):
                continue
            unknown.add(pair)

        assert not unknown, (
            f"{rel} quotes {sorted(unknown)} over the event log; the recorded "
            f"measurements are {sorted(permitted)}. Either the document is stale "
            f"or a new measurement was published without being pinned."
        )
        if found_any:
            checked += 1

    assert checked >= 2, (
        f"only {checked} document(s) actually quoted a measurement; this check "
        f"is close to vacuous."
    )


def test_the_commit_population_snapshot_is_consistent_with_the_live_log():
    """Monotonic, for the same reason as the coverage snapshot beside it.

    This assertion was written as EQUALITY, which was a time bomb: every
    iterate's F5b appends a ``work_completed`` event, so the very next one — in
    this repo or merging ahead of this branch — takes the log past the frozen
    denominator and reddens ``integration-tests`` for a change that did nothing
    wrong. Worse than the case the sibling docstring warns about, because it
    fires on ANY work event rather than only FR-linked ones.

    "Must move in lockstep" is a statement about the two figures sharing a
    denominator at the moment they were measured, not a licence to freeze that
    denominator. Anti-drift between DOCUMENT and CONSTANT is enforced by
    :func:`test_every_measurement_quoted_over_the_event_log_is_current`, which
    is unaffected by this relaxation.
    """
    events, _ = read_work_events(_REPO)
    with_commit = sum(1 for e in events if e.get("commit"))

    assert len(events) >= COVERAGE_WORK_EVENTS, (
        f"the log holds {len(events)} completed changes, fewer than the "
        f"{COVERAGE_WORK_EVENTS} published as the shared denominator. An "
        f"append-only log cannot shrink, so either the snapshot was never "
        f"measured or records were lost."
    )
    assert with_commit >= COMMIT_POPULATED_EVENTS, (
        f"{with_commit} events carry a commit hash, fewer than the "
        f"{COMMIT_POPULATED_EVENTS} ADR-110 publishes — the same impossibility "
        f"on the commit-bearing subset."
    )
    assert with_commit * 2 < len(events), (
        f"{with_commit} of {len(events)} events now carry a commit hash — no "
        f"longer the minority ADR-110 cites as its reason for adding no schema "
        f"field. Rewrite that paragraph; do not relax this assertion."
    )


def test_the_recorded_coverage_is_consistent_with_the_live_log():
    """Monotonic, not equality — an append-only log only grows.

    An equality pin would turn the NEXT unrelated iterate that links an FR red:
    a gate punishing correct behaviour. What must hold is that the snapshot was
    really taken from this log (never above it) and that the qualitative claim
    the prose makes — a MINORITY of recorded changes carry a requirement link —
    is still true. If the share ever reaches a majority the shipped sentence has
    become false and must be rewritten.
    """
    live = coverage_summary(_REPO)

    assert live.work_events >= COVERAGE_WORK_EVENTS, (
        f"the log now holds {live.work_events} completed changes, fewer than the "
        f"{COVERAGE_WORK_EVENTS} recorded. An append-only log cannot shrink, so "
        f"either the snapshot was never measured or records were lost."
    )
    assert live.fr_linked_events >= COVERAGE_FR_LINKED_EVENTS, (
        f"{live.fr_linked_events} FR-linked events now, {COVERAGE_FR_LINKED_EVENTS} "
        f"recorded — the same impossibility on the linked subset."
    )
    assert live.fr_linked_events * 2 < live.work_events, (
        f"{live.fr_linked_events} of {live.work_events} recorded changes now name "
        f"a requirement — no longer the minority the shipped prose describes. "
        f"Rewrite the sentence in ADR-110, the mini-plan, the decision log and "
        f"the changelog drop; do not relax this assertion."
    )


def test_the_coverage_snapshot_includes_this_runs_own_event():
    """"As of this change" is checkable, not implied.

    The figure was re-measured after this run's own finalization event landed,
    which is why it reads 61/342 and not the 60/341 measured mid-build.
    """
    history = change_history_for_fr(_REPO, "FR-01.10")
    assert any(c.label == COVERAGE_AS_OF_RUN for c in history.changes), (
        f"{COVERAGE_AS_OF_RUN} is recorded as the last run included in the "
        f"coverage snapshot, but its own event does not appear against FR-01.10."
    )

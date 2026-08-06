"""Disposition rules for the outbox sweep — the four outcomes of ``decide``.

iterate-2026-08-06-triage-validate-deadends (trg-b854805c). ``decide`` used to
have three outcomes and only two of them made progress, so ANY line the sweep
could not place took the whole outbox down with it — permanently, because the
remedy the block named ("deliver main by push / merge") is unreachable in a
workflow where main is only ever fast-forwarded from origin. The buffer holding
everything it stranded is gitignored: one ``git clean -xfd`` from empty.

These tests pin the proportional model that replaced it. Every error class gets
exactly one disposition, and ``block`` now means only "corruption I must not
paper over":

* **hold**       — not deliverable YET (its append is in main's tracked log).
                   Kept in the outbox, retried next sweep; the rest is delivered.
* **quarantine** — not deliverable EVER (no append anywhere, or no usable id).
* **block**      — genuine corruption, or a defect in the worktree-tracked log
                   the sweep cannot rewrite. Always names a reachable remedy.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
from lib.sweep_quarantine import decide  # noqa: E402
from lib.sweep_result import SweepResult, sweep_warnings  # noqa: E402

MAIN_ONLY = "trg-in-main"        # its append lives in main's TRACKED log
GHOST = "trg-ghost"              # its append exists nowhere
PENDING = "trg-pending"          # an ordinary, perfectly deliverable append
KNOWN = frozenset({MAIN_ONLY})

NO_ID = '{"event":"status","ts":"2026-06-08T00:00:01Z","newStatus":"dismissed"}'
INT_ID = '{"event":"status","id":7,"ts":"2026-06-08T00:00:01Z","newStatus":"dismissed"}'


def _tracked() -> list[str]:
    return [h.HEADER, h.item("trg-other")]


# --- hold: finding 17, the absorbing state ----------------------------------


def test_protected_status_is_held_not_blocked() -> None:
    """AC4. The dismiss is legitimate — its append is real, it just is not
    reachable from this branch yet. It must never be quarantined (that destroys
    the operator's decision and the item resurrects forever, reproduced live
    2026-07-14) and must no longer block (that stranded everything else)."""
    dismiss = h.status(MAIN_ONLY, "dismissed")

    d = decide(_tracked(), [dismiss], "\n", known_append_ids=KNOWN)

    assert d.action == "hold", d
    assert d.held_lines == [dismiss]
    assert dismiss not in d.candidates, "the operator's dismiss was made a quarantine candidate"


def test_hold_delivers_the_rest_of_the_outbox() -> None:
    """AC4. The whole point: one unplaceable line no longer strands unrelated work."""
    dismiss = h.status(MAIN_ONLY, "dismissed")
    pending = h.item(PENDING)

    d = decide(_tracked(), [dismiss, pending], "\n", known_append_ids=KNOWN)

    assert d.action == "hold"
    assert d.held_lines == [dismiss]
    assert d.materialized_outbox == [pending]
    assert pending in d.deduped_text and dismiss not in d.deduped_text


# --- quarantine: finding 18, the un-selectable status -----------------------


def test_unidentified_status_is_quarantined() -> None:
    """AC6. A status with no usable id was a dead end: recorded as an error, but
    absent from ``orphan_status_ids``, so the quarantine could not select it (no
    id) and the repair could not fix it (the JSON is valid). It is inert to every
    reader — ``read_all_items`` skips a non-``str`` id — so quarantining it
    destroys nothing observable."""
    for bad in (NO_ID, INT_ID):
        pending = h.item(PENDING)

        d = decide(_tracked(), [bad, pending], "\n", known_append_ids=KNOWN)

        assert d.action == "quarantine", (bad, d)
        assert d.candidates == [bad], bad
        assert d.materialized_outbox == [pending], bad


def test_genuine_orphan_is_still_quarantined() -> None:
    """The pre-existing class (#303) is untouched by the new dispositions."""
    orphan = h.status(GHOST, "dismissed")

    d = decide(_tracked(), [orphan], "\n", known_append_ids=KNOWN)

    assert d.action == "quarantine" and d.candidates == [orphan]


# --- the two can co-occur ----------------------------------------------------


def test_hold_and_quarantine_co_occur() -> None:
    """AC7. ``action`` is a report, not the mechanism — both lists are always
    populated, so a sweep carrying one of each loses neither."""
    dismiss = h.status(MAIN_ONLY, "dismissed")
    orphan = h.status(GHOST, "dismissed")
    pending = h.item(PENDING)

    d = decide(_tracked(), [dismiss, orphan, pending], "\n", known_append_ids=KNOWN)

    assert d.candidates == [orphan]
    assert d.held_lines == [dismiss]
    assert d.materialized_outbox == [pending]
    assert d.action == "quarantine"  # the stronger disposition names the run


# --- AC10: the partition is total, ordered and multiplicity-preserving -------


def test_dispositions_partition_the_outbox() -> None:
    """AC10, exhaustiveness half. Every outbox line has exactly one disposition."""
    outbox = [
        h.status(MAIN_ONLY, "dismissed"), h.item(PENDING),
        h.status(GHOST, "dismissed"), NO_ID,
    ]

    d = decide(_tracked(), outbox, "\n", known_append_ids=KNOWN)

    assert sorted(d.materialized_outbox + d.candidates + d.held_lines) == sorted(outbox)
    assert len(d.materialized_outbox) + len(d.candidates) + len(d.held_lines) == len(outbox)


def test_dispositions_preserve_input_order_within_each_list() -> None:
    """AC10, ORDER half. ``sorted()`` above proves multiplicity but discards order,
    so this pins it directly: two DISTINCT lines routed to the same list keep their
    input sequence. An index partition gives this for free; a set-difference or a
    per-class re-scan would not."""
    outbox = [
        h.status(GHOST, "dismissed"), h.item("trg-p1"), NO_ID,
        h.status(MAIN_ONLY, "dismissed"), h.item("trg-p2"), INT_ID,
        h.status("trg-ghost-2", "dismissed"), h.status(MAIN_ONLY, "snoozed"),
    ]

    d = decide(_tracked(), outbox, "\n", known_append_ids=KNOWN)

    assert d.candidates == [
        h.status(GHOST, "dismissed"), NO_ID, INT_ID, h.status("trg-ghost-2", "dismissed"),
    ]
    assert d.held_lines == [h.status(MAIN_ONLY, "dismissed"), h.status(MAIN_ONLY, "snoozed")]
    assert d.materialized_outbox == [h.item("trg-p1"), h.item("trg-p2")]


def test_duplicate_status_records_keep_multiplicity() -> None:
    """AC10. A set-difference partition would collapse two identical buffered
    records into one and silently change what is written back."""
    orphan = h.status(GHOST, "dismissed")

    d = decide(_tracked(), [orphan, orphan], "\n", known_append_ids=KNOWN)

    assert d.candidates == [orphan, orphan]
    assert d.materialized_outbox == []


def test_held_is_not_in_the_quarantine_removal_set() -> None:
    """AC5, at the unit level. ``sweep_outbox`` removes ``candidates`` from the
    persisted outbox; a held line appearing there is exactly the data loss this
    change exists to prevent."""
    dismiss = h.status(MAIN_ONLY, "dismissed")
    orphan = h.status(GHOST, "dismissed")

    d = decide(_tracked(), [dismiss, orphan], "\n", known_append_ids=KNOWN)

    assert dismiss not in d.candidates
    assert d.held_lines == [dismiss]


# --- AC11: glued lines the sweep cannot disposition per record ---------------


def test_valid_glued_line_is_materialized_not_dispositioned() -> None:
    """AC11. ``multi_record`` is advisory metadata and never blocks on its own: a
    glued line whose records are all fine raises no validator error at all, so
    the run is ``clean`` (external plan review r3, openai #4)."""
    glued = h.item("trg-x") + h.item("trg-y")

    d = decide(_tracked(), [glued, h.item(PENDING)], "\n", known_append_ids=KNOWN)

    assert d.action == "clean", d
    assert d.candidates == [] and d.held_lines == []
    assert d.materialized_outbox == [glued, h.item(PENDING)], "the glued line was not delivered"
    assert glued in d.deduped_text



# --- AC8: the operator is told ------------------------------------------------


def test_sweep_warnings_reports_held() -> None:
    """AC8. Silence is how the earlier quarantine data loss stayed invisible for
    as long as it did; a withheld line gets the same treatment. Counts only."""
    notes = sweep_warnings(SweepResult(status="committed", swept=1, held=2))

    assert any("held" in n.lower() and "2" in n for n in notes), notes


def test_sweep_warnings_reports_held_on_a_quiet_sweep() -> None:
    """AC8. A held line that never becomes reachable stays buffered forever, and
    a sweep with nothing else to do is exactly when nobody would notice."""
    notes = sweep_warnings(SweepResult(status="no_change", reason="no_branch_change", held=1))

    assert any("held" in n.lower() for n in notes), notes

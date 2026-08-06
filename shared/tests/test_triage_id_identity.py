"""Only ``str`` ids participate in triage identity — on BOTH event kinds (AC13).

iterate-2026-08-06-triage-validate-deadends (trg-b854805c). Finding 18 was a
``status`` with a missing or non-``str`` id that could be neither quarantined (no
id to select) nor repaired (the JSON is valid). Fixing only the status side left
``classify_triage_text`` as the odd one out: two OTHER places had already decided
that a non-``str`` id carries no identity —

* ``triage.read_all_items`` skips it in pass 1 AND pass 2, so neither an append
  nor a status with such an id can affect any item;
* ``churn_merge.dedup_triage_lines._append_id`` returns ``None`` for one, so the
  dedup never collapses those appends.

The validator disagreeing with both is what produced two further defects, pinned
here: a ``TypeError: unhashable`` crash raised from inside the sweep's own lock,
and a log that could never be delivered again because two appends sharing a
non-``str`` id were reported as a duplicate the dedup will never collapse.

Split from ``test_sweep_quarantine_dispositions`` so both modules stay under the
300-LOC guideline; that module owns the four dispositions, this one owns the
identity rule they select on.
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
from lib.triage_validate import classify_triage_text  # noqa: E402

PENDING = "trg-pending"
KNOWN = frozenset({"trg-in-main"})


def _tracked() -> list[str]:
    return [h.HEADER, h.item("trg-other")]


# --- AC13.2: the crash, on both event kinds ----------------------------------


def test_an_unhashable_status_id_does_not_crash_the_sweep() -> None:
    """An ``id`` may be any JSON value. ``[] in frozenset(...)`` raises TypeError:
    unhashable — from inside the sweep's own lock, which is strictly worse than
    the dead end this change exists to remove. Every membership test now checks
    ``isinstance`` FIRST, and that evaluation order is what this pins: without it
    the test raises rather than failing an assertion."""
    unhashable = '{"event":"status","id":[],"ts":"2026-06-08T00:00:01Z","newStatus":"dismissed"}'

    d = decide(_tracked(), [unhashable, h.item(PENDING)], "\n", known_append_ids=KNOWN)

    assert d.action == "quarantine", d
    assert d.candidates == [unhashable]
    assert d.materialized_outbox == [h.item(PENDING)]


def test_an_unhashable_append_id_does_not_crash_the_validator() -> None:
    """The same hazard on the append side, where ``append_ids.add(iid)`` raised."""
    weird_append = '{"event":"append","id":{"a":1},"status":"triage"}'

    d = decide(_tracked(), [weird_append, h.item(PENDING)], "\n", known_append_ids=KNOWN)

    assert d.action == "clean", d


# --- AC13.3: the fourth dead end of finding 18's family ----------------------


def test_duplicate_non_str_append_id_is_no_longer_undeliverable() -> None:
    """Two non-identical appends sharing ``"id": 7`` were reported as a duplicate
    that ``dedup_triage_lines`` will never collapse (``_append_id`` returns None
    for a non-str id) — so that log could never be delivered again, by anything."""
    dup = '{"event":"append","id":7,"status":"triage"}'
    text = "\n".join([h.HEADER, dup, dup.replace("triage", "open")]) + "\n"

    assert classify_triage_text(text).errors == []


# --- AC13 / R9: the one shape that stops being tolerated ---------------------


def test_matched_non_str_id_pair_loses_its_status() -> None:
    """The ONE genuine loss of tolerance, asserted directly rather than inferred.

    An ``append`` + ``status`` pair sharing a non-``str`` id validated CLEAN before
    (the old append set accepted ``7``, so the status found its append) and now has
    its status quarantined. Accepted, because the pair was already inert: reader
    pass 1 skips the append, so no item exists for pass 2 to overlay. Nothing
    observable is destroyed — and the append itself still ships."""
    append_7 = '{"event":"append","id":7,"ts":"2026-06-08T00:00:00Z","status":"triage"}'
    status_7 = '{"event":"status","id":7,"ts":"2026-06-08T00:00:01Z","newStatus":"dismissed"}'

    d = decide(_tracked(), [append_7, status_7], "\n", known_append_ids=KNOWN)

    assert d.action == "quarantine", d
    assert d.candidates == [status_7]
    assert d.materialized_outbox == [append_7], "the append was withheld too"

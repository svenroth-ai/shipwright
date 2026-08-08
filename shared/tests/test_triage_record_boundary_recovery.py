"""Record-boundary recovery + durable read — IT-1 audit findings 21 and 5.

Leaf-level regression home for iterate-2026-08-06-p2-19c-corruption-absence
(card ``trg-8652bf24``). The durable-read half is ``test_triage_durable_read.py``; the store-level halves
are ``test_triage_corruption_visibility.py``, ``test_triage_reader_integrity.py``
and ``test_triage_delivery_visibility.py``.

* **AC1 / finding 21** — boundary recovery ran one way only: an unrecoverable
  *prefix* sent the whole rest of the physical line to the remainder, discarding
  every valid record behind it. The documented primary cause (a predecessor
  truncated mid-write, then appended onto) has exactly that shape, and the two
  pre-existing covering tests exercise the other two shapes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.jsonl_records import split_records  # noqa: E402
from lib.triage_integrity import is_triage_record  # noqa: E402


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _rec(item_id: str, **extra) -> dict:
    """A COMPLETE append record — every key ``append_triage_item`` always emits.

    The predicate now requires the full writer-emitted key set, so a minimal
    ``{"event","id","ts"}`` stub is not a record and must not be used as a fixture:
    an external code review forged exactly such a stub inside wreckage and the
    resync surfaced it. Fixtures therefore look like what the writer writes.
    """
    return {
        "event": "append", "id": item_id, "ts": "2026-01-01T00:00:00Z",
        "source": "manual", "severity": "low", "kind": "bug",
        "title": "t", "detail": "d", "status": "triage", **extra,
    }


def _split(line: str):
    """Split the way the triage store does — with its record predicate."""
    return split_records(line, is_record=is_triage_record)


# ---------------------------------------------------------------------------
# AC1 (finding 21) — recovery must work FORWARD past a damaged prefix
# ---------------------------------------------------------------------------

def test_valid_record_after_a_truncated_predecessor_is_recovered() -> None:
    """The documented primary cause, which the pre-fix reader lost whole."""
    truncated = '{"event":"append","id":"trg-aaaa","ts":"1'
    good = _rec("trg-bbbb")
    records, remainder = _split(truncated + _j(good))

    assert [r["id"] for r in records] == ["trg-bbbb"]
    # The damaged span is reported as ITSELF, not as "everything to end of line".
    assert remainder == truncated


def test_resync_never_fabricates_a_record_from_inside_the_damaged_prefix() -> None:
    """A brace nested in the damaged prefix must not become an independent record.

    Raised as a high finding by the external plan review and reproduced against
    a naive "advance to the next ``{``" rule, which decoded ``{"b":1}`` out of
    the wreckage and returned it as a record.
    """
    damaged = '{"a":{"b":1},"c":"tr'
    good = _rec("trg-real")
    records, remainder = _split(damaged + _j(good))

    assert [r.get("id") for r in records] == ["trg-real"]
    assert {"b": 1} not in records
    assert remainder == damaged


def test_resync_rejects_a_complete_object_nested_in_the_damaged_prefix() -> None:
    """The round-2 high finding, reproduced against the round-1 fix and closed.

    "The candidate's run must reach end-of-line" is necessary but NOT sufficient:
    when the truncated predecessor's last field is itself an object, the run
    starting at THAT object consumes it plus the genuine append and reaches EOL,
    so ``{"embedded":1}`` was surfaced as a triage record. Requiring every object
    in the run to satisfy the store's record predicate rejects it.
    """
    damaged = '{"event":"append","id":"trg-1","meta":{"embedded":1}'
    good = _rec("trg-real")
    records, remainder = _split(damaged + _j(good))

    assert [r.get("id") for r in records] == ["trg-real"]
    assert all("embedded" not in r for r in records)
    assert remainder == damaged


def test_without_a_predicate_recovery_fails_closed() -> None:
    """No predicate means no resync — syntax alone cannot find a record boundary.

    The leaf serves two logs with different record shapes, so it refuses to guess.
    A caller that passes nothing gets exactly the pre-2026-08 behaviour.
    """
    truncated = '{"event":"append","id":"trg-aaaa","ts":"1'
    good = _rec("trg-bbbb")
    records, remainder = split_records(truncated + _j(good))
    assert records == []
    assert remainder == truncated + _j(good)


def test_resync_rejects_a_minimal_forged_record_nested_in_the_prefix() -> None:
    """The FOURTH fabrication shape, from the external code review. Reproduced.

    A predicate of "has an `event` and a string `id`" is satisfied by a two-key
    object, so wreckage containing ``{"meta":{"event":"append","id":"forged"}``
    followed by a genuine append let the run consume both and surfaced ``forged``.
    Requiring every key the writer always emits closes it: the nested stub has no
    ``ts``/``title``/``severity``/``kind``/``source``/``status``.

    This is the third narrowing of this predicate. Each previous version was
    justified by a property of today's data; this one is read off the writers.
    """
    damaged = '{"meta":{"event":"append","id":"forged"}'
    good = _rec("trg-real")
    records, remainder = _split(damaged + _j(good))

    assert [r.get("id") for r in records] == ["trg-real"]
    assert all(r.get("id") != "forged" for r in records)
    assert remainder == damaged


def test_a_status_shaped_stub_is_also_rejected() -> None:
    """The same hole via the other event kind."""
    damaged = '{"meta":{"event":"status","id":"forged"}'
    good = _rec("trg-real")
    records, remainder = _split(damaged + _j(good))
    assert [r.get("id") for r in records] == ["trg-real"]
    assert remainder == damaged


def test_a_complete_status_record_after_damage_is_still_recovered() -> None:
    """Narrowing must not cost the genuine `status` recovery path."""
    damaged = '{"event":"append","id":"trg-1","ts":"1'
    flip = {"event": "status", "id": "trg-real", "ts": "2026-01-02T00:00:00Z",
            "newStatus": "dismissed", "by": "webui", "reason": "done"}
    records, remainder = _split(damaged + _j(flip))
    assert [r["id"] for r in records] == ["trg-real"]
    assert remainder == damaged


def test_a_foreign_shaped_object_is_not_recovered_as_a_triage_record() -> None:
    """An events-log record (keyed on ``type``) is not a triage record."""
    damaged = '{"event":"append","id":"trg-1","x":"tr'
    foreign = {"type": "work_completed", "id": "evt-1"}
    records, remainder = _split(damaged + _j(foreign))
    assert records == []
    assert remainder == damaged + _j(foreign)


def test_unrecoverable_line_with_nothing_valid_behind_it_is_unchanged() -> None:
    """Pure garbage keeps today's behaviour: no records, whole span reported."""
    records, remainder = _split("}{garbage no records here")
    assert records == []
    assert remainder == "}{garbage no records here"


def test_valid_record_followed_by_a_damaged_tail_still_reports_the_tail() -> None:
    good = _rec("trg-ok")
    records, remainder = _split(_j(good) + '{"broken":')
    assert [r["id"] for r in records] == ["trg-ok"]
    assert remainder == '{"broken":'


def test_a_scalar_between_two_records_does_not_swallow_the_second() -> None:
    """Only objects are records; a scalar is a fragment, not a stop sign."""
    a = _rec("trg-1111")
    b = _rec("trg-2222")
    records, remainder = _split(_j(a) + "42" + _j(b))
    assert [r["id"] for r in records] == ["trg-1111", "trg-2222"]
    assert remainder == "42"


def _decoys(n: int) -> str:
    """``n`` candidate ``{`` positions that every predicate must reject."""
    return '{"event":"append","id":"trg-1","x":"' + ("{" * n)


def test_a_record_within_the_resync_budget_is_recovered() -> None:
    """Below the cap, the genuine record behind the decoys is still found."""
    good = _rec("trg-inrange")
    records, _ = _split(_decoys(10) + _j(good))
    assert [r["id"] for r in records] == ["trg-inrange"]


def test_a_record_beyond_the_resync_budget_is_not_recovered() -> None:
    """Above the cap, the scan stops — and this is the pin that makes the cap real.

    Deleting ``_MAX_RESYNC_ATTEMPTS`` makes THIS test fail (the record would be
    found), while the paired test above fails if the cap is set too low. A test
    using only unmatchable decoys would pass with or without the cap, since both
    end in "nothing recovered" — the first version of this test did exactly that
    and was caught by the Stage-1 spec review.

    Each candidate re-parses the remainder, so an unbounded scan is O(n^2) on a
    malformed line; the cap degrades to reporting the whole span, never to a hang.
    """
    from lib.jsonl_records import _MAX_RESYNC_ATTEMPTS

    good = _rec("trg-toofar")
    line = _decoys(_MAX_RESYNC_ATTEMPTS + 5) + _j(good)
    records, remainder = _split(line)
    assert records == []
    assert remainder == line


# --- amend records (iterate-2026-08-08-triage-amend-event, AC7) -----------

def test_a_complete_amend_record_is_a_record() -> None:
    assert is_triage_record({
        "event": "amend", "id": "trg-1", "ts": "t", "by": "cli", "title": "x",
    })


def test_an_amend_missing_a_required_key_is_not_a_record() -> None:
    assert not is_triage_record({"event": "amend", "ts": "t", "by": "cli", "title": "x"})


def test_a_key_complete_but_content_empty_amend_is_not_a_record() -> None:
    """The forged-record gap external plan review flagged HIGH: an amend naming
    none of title/detail/severity/kind is key-complete but empty, and would
    otherwise be indistinguishable from a valid minimal amend during resync."""
    assert not is_triage_record({"event": "amend", "id": "trg-1", "ts": "t", "by": "cli"})


def test_resync_rejects_a_content_empty_amend_nested_in_the_prefix() -> None:
    """The forged-record gap, in the SAME wreckage shape the other event kinds
    are already pinned against: key-complete is not enough, content must be too."""
    damaged = '{"meta":{"event":"amend","id":"forged","ts":"t","by":"cli"}'
    good = _rec("trg-real")
    records, remainder = _split(damaged + _j(good))
    assert [r.get("id") for r in records] == ["trg-real"]
    assert all(r.get("id") != "forged" for r in records)
    assert remainder == damaged

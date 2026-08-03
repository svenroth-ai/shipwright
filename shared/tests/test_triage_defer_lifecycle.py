"""The parked-entry lifecycle, as pure policy — `lib/triage_defer.py`.

RED-first for iterate-2026-08-01-triage-defer-lifecycle. Everything here is a
pure function over a date and a dict: no store, no lock, no clock. The clock is
read once at the store boundary and passed in, which is what makes the
UTC-day-boundary cases below expressible at all (AC-28).

Store/CLI behaviour has separate tests; this file pins their shared rules.
"""

from __future__ import annotations

import sys
from datetime import date, timezone
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.triage_defer import (  # noqa: E402
    AUTO_RESOLVABLE_STATUSES,
    DEFERRABLE_STATUSES,
    DEFERRED_TOP_N,
    DUE_FIELD,
    REVISIT_FIELD,
    UNPARKABLE_STATUSES,
    apply_revisit_expiry,
    is_auto_resolvable,
    is_due,
    now_utc,
    parse_revisit_date,
    resolve_revisit,
    sort_deferred,
    suppresses_reimport,
)

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


# ---------------------------------------------------------------------------
# AC-21 — the date is parsed strictly
# ---------------------------------------------------------------------------

def test_a_plain_calendar_date_parses() -> None:
    assert parse_revisit_date("2026-09-01") == date(2026, 9, 1)


def test_a_leap_day_that_exists_parses() -> None:
    assert parse_revisit_date("2028-02-29") == date(2028, 2, 29)


@pytest.mark.parametrize(
    "raw",
    [
        "2026-02-30",            # not a real calendar date
        "2026-13-01",            # month out of range
        "2026-09-01T00:00:00Z",  # a timestamp, not a date
        " 2026-09-01",           # leading whitespace
        "2026-09-01 ",           # trailing whitespace
        "2026-9-1", "2026-09- 1",  # unpadded / internally space-padded
        "2026-09",               # partial
        "26-09-01",              # two-digit year
        "",
        "next tuesday",
        None,
        20260901,                # not a string at all
        ["2026-09-01"],
    ],
    ids=[
        "impossible-day", "impossible-month", "timestamp", "leading-space",
        "trailing-space", "unpadded", "internal-space", "partial", "short-year", "empty",
        "prose", "none", "int", "list",
    ],
)
def test_anything_that_is_not_exactly_yyyy_mm_dd_is_refused(raw) -> None:
    """A permissive parser would let the CLI's promise and the stored
    classification diverge — an accepted timestamp would round-trip as a date
    the operator never typed (external plan review, round 2 finding #5)."""
    assert parse_revisit_date(raw) is None


# ---------------------------------------------------------------------------
# AC-3a — a park named for day D is due from 00:00:00 UTC on D
# ---------------------------------------------------------------------------

def test_the_day_before_the_revisit_date_is_not_due() -> None:
    assert is_due("2026-09-01", date(2026, 8, 31)) is False


def test_the_revisit_date_itself_is_due() -> None:
    """`>=`, not `>`: an operator who says 'bring this back on Sept 1' wants it
    ON Sept 1. Both external reviewers raised this boundary independently."""
    assert is_due("2026-09-01", date(2026, 9, 1)) is True


def test_the_day_after_the_revisit_date_is_due() -> None:
    assert is_due("2026-09-01", date(2026, 9, 2)) is True


@pytest.mark.parametrize(
    "raw", [None, "", "not-a-date", "2026-02-30", 42],
    ids=["missing", "empty", "prose", "impossible", "int"],
)
def test_an_unreadable_revisit_value_is_never_due(raw) -> None:
    """AC-7's conservative direction. An unreadable date must not silently
    re-open an entry; it stays parked, visible, and reversible."""
    assert is_due(raw, date(2099, 1, 1)) is False


def test_now_utc_is_timezone_aware_and_utc() -> None:
    """The one clock read in the whole lifecycle. A naive local datetime here
    would move the day boundary by the developer's offset (round 2, #5)."""
    stamp = now_utc()
    assert stamp.tzinfo is not None
    assert stamp.utcoffset() == timezone.utc.utcoffset(None)


# ---------------------------------------------------------------------------
# AC-2 / AC-3 / AC-24 — expiry is applied to the resolved view, and only there
# ---------------------------------------------------------------------------

def _parked(item_id: str, revisit: object, **extra) -> dict:
    return {
        "id": item_id, "status": "snoozed", "severity": "medium",
        REVISIT_FIELD: revisit, **extra,
    }


def test_a_park_whose_date_has_not_arrived_still_reads_as_parked() -> None:
    [item] = apply_revisit_expiry([_parked("trg-a", "2026-09-01")],
                                  today=date(2026, 8, 31))
    assert item["status"] == "snoozed"
    assert item[DUE_FIELD] is False


def test_a_park_whose_date_has_passed_reads_as_open() -> None:
    [item] = apply_revisit_expiry([_parked("trg-a", "2026-09-01")],
                                  today=date(2026, 9, 2))
    assert item["status"] == "triage"
    assert item[DUE_FIELD] is True


def test_an_expired_park_keeps_its_revisit_date_so_it_stays_distinguishable(
) -> None:
    """AC-19(c). An entry open because its park expired still carries the date;
    an entry an operator un-parked carries none. That difference is what makes
    a separate `storedStatus` field unnecessary (round 3, #3)."""
    [item] = apply_revisit_expiry([_parked("trg-a", "2026-09-01")],
                                  today=date(2026, 9, 2))
    assert item[REVISIT_FIELD] == "2026-09-01"


def test_expiry_never_touches_a_status_other_than_parked() -> None:
    """A `dismissed` entry carrying a stale revisit date (hand-edited, or a
    park later dismissed by a producer that wrote no date) must not be dragged
    back open by it."""
    items = [
        {"id": "trg-d", "status": "dismissed", REVISIT_FIELD: "2020-01-01"},
        {"id": "trg-p", "status": "promoted", REVISIT_FIELD: "2020-01-01"},
        {"id": "trg-t", "status": "triage", REVISIT_FIELD: None},
    ]
    by_id = {i["id"]: i for i in apply_revisit_expiry(items,
                                                      today=date(2099, 1, 1))}
    assert by_id["trg-d"]["status"] == "dismissed"
    assert by_id["trg-p"]["status"] == "promoted"
    assert by_id["trg-t"]["status"] == "triage"


def test_every_item_carries_the_two_fields_even_when_never_parked() -> None:
    """Same shape rule `read_all_items` already applies to statusBy /
    statusReason / promotedTaskId: present on every item, defaulted. A
    consumer with a static type must not meet two shapes."""
    [item] = apply_revisit_expiry([{"id": "trg-t", "status": "triage"}],
                                  today=date(2026, 1, 1))
    assert item[REVISIT_FIELD] is None
    assert item[DUE_FIELD] is False


def test_resolving_one_park_returns_a_copy() -> None:
    stored = _parked("trg-a", "2026-09-01")
    resolved = resolve_revisit(stored, today=date(2026, 9, 2))
    assert resolved["status"] == "triage"
    assert stored["status"] == "snoozed"


def test_one_today_decides_every_item_in_the_batch() -> None:
    """AC-28. Two entries either side of the boundary resolve against the SAME
    instant — never one against 23:59 and its neighbour against 00:00."""
    items = [_parked("trg-a", "2026-09-01"), _parked("trg-b", "2026-09-02")]
    by_id = {i["id"]: i for i in apply_revisit_expiry(items,
                                                      today=date(2026, 9, 1))}
    assert by_id["trg-a"]["status"] == "triage"
    assert by_id["trg-b"]["status"] == "snoozed"


# ---------------------------------------------------------------------------
# AC-22 / AC-27 — the deferred order is TOTAL
# ---------------------------------------------------------------------------

def test_deferred_entries_sort_soonest_return_first() -> None:
    items = [
        _parked("trg-c", "2026-12-01"),
        _parked("trg-a", "2026-09-01"),
        _parked("trg-b", "2026-10-01"),
    ]
    assert [i["id"] for i in sort_deferred(items, SEVERITY_RANK)] == [
        "trg-a", "trg-b", "trg-c",
    ]


def test_entries_without_a_readable_date_sort_after_every_dated_one() -> None:
    items = [
        _parked("trg-none", None),
        _parked("trg-bad", "not-a-date"),
        _parked("trg-far", "2099-01-01"),
    ]
    assert [i["id"] for i in sort_deferred(items, SEVERITY_RANK)][0] == "trg-far"


def test_same_date_breaks_by_severity_critical_first() -> None:
    items = [
        _parked("trg-low", "2026-09-01", severity="low"),
        _parked("trg-crit", "2026-09-01", severity="critical"),
        _parked("trg-med", "2026-09-01", severity="medium"),
    ]
    assert [i["id"] for i in sort_deferred(items, SEVERITY_RANK)] == [
        "trg-crit", "trg-med", "trg-low",
    ]


def test_an_unknown_severity_sorts_last_not_first() -> None:
    """A hand-edited severity must not jump the queue ahead of a real critical
    just because it is unknown to the rank map (round 4, #1)."""
    items = [
        _parked("trg-weird", "2026-09-01", severity="URGENT!!"),
        _parked("trg-info", "2026-09-01", severity="info"),
    ]
    assert [i["id"] for i in sort_deferred(items, SEVERITY_RANK)] == [
        "trg-info", "trg-weird",
    ]


def test_identical_date_and_severity_break_by_id_so_the_order_is_total() -> None:
    """Without a final tie-break the capped subset can differ between two runs
    over the same data — the operator would see a different set each time."""
    items = [
        _parked("trg-zzz", "2026-09-01"), _parked("trg-aaa", "2026-09-01"),
    ]
    assert [i["id"] for i in sort_deferred(items, SEVERITY_RANK)] == [
        "trg-aaa", "trg-zzz",
    ]


def test_sorting_does_not_mutate_the_caller_list() -> None:
    items = [_parked("trg-b", "2026-10-01"), _parked("trg-a", "2026-09-01")]
    sort_deferred(items, SEVERITY_RANK)
    assert [i["id"] for i in items] == ["trg-b", "trg-a"]


def test_a_producer_may_close_an_open_or_a_parked_entry() -> None:
    """AC-10: one declared answer, so a producer added later cannot hold a
    different one. `dismissed` and `promoted` are NOT in it — a producer never
    reverses a decision that ended an entry's life."""
    assert set(AUTO_RESOLVABLE_STATUSES) == {"triage", "snoozed"}
    assert is_auto_resolvable(["triage"]) is False


def test_reimport_policy_covers_identity_lifecycle_and_recency() -> None:
    base = {
        "status": "triage", "source": "github", "dedupKey": "same",
        "commit": "abc", "originalTs": "2020-01-01T00:00:00Z",
    }
    args = dict(source="github", dedup_key="same", commit="abc",
                match_commit=True)
    assert suppresses_reimport(base, cutoff=None, **args) is True
    assert suppresses_reimport(base, cutoff=2_000_000_000, **args) is False
    assert suppresses_reimport({**base, "status": "snoozed"},
                               cutoff=2_000_000_000, **args) is True
    assert suppresses_reimport({**base, "revisitDue": True},
                               cutoff=2_000_000_000, **args) is True
    assert suppresses_reimport({**base, "dedupKey": "other"},
                               cutoff=None, **args) is False


def test_an_entry_can_be_parked_from_open_or_re_parked_from_parked() -> None:
    """AC-23. Without `snoozed` here a mistyped date could only be corrected by
    un-parking first, and AC-9a would describe a race that cannot occur."""
    assert set(DEFERRABLE_STATUSES) == {"triage", "snoozed"}


def test_only_a_parked_entry_can_be_un_parked() -> None:
    assert set(UNPARKABLE_STATUSES) == {"snoozed"}


def test_the_display_cap_is_a_positive_number_both_surfaces_can_share() -> None:
    assert isinstance(DEFERRED_TOP_N, int) and DEFERRED_TOP_N > 0

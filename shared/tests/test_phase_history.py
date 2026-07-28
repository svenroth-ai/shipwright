"""``lib.phase_history`` — reading a completion's two clocks.

External plan review (openai R2) asked for this contract to be stated and
validated rather than assumed at the call site, because the repo already has
more than one timestamp shape in the wild and a wrong assumption here becomes a
wrong verdict in Canon C3.

The load-bearing property is :class:`RecordedTime`: a bare ``YYYY-MM-DD`` pins a
DAY, not an instant. Reading it as midnight UTC — which this module did until the
review cascade caught it — made every same-day comparison answer confidently and
wrongly, and that is what let a phase which skipped its C3 step read as
legitimately superseded.

Reading the RECORD (``latest_completion``) lives in
``test_phase_history_records.py``; this file is the timekeeping alone.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.phase_history import (  # noqa: E402
    RecordedTime,
    entry_anchor,
    entry_wall_time,
    parse_iso_utc,
)


def _at(text: str) -> datetime:
    moment = parse_iso_utc(text)
    assert moment is not None
    return moment


# --- both real shapes ---------------------------------------------------------

def test_the_at_shape_pins_an_instant():
    """What every phase producer writes since this iterate."""
    when = entry_wall_time({"run_id": "r", "at": "2026-07-27T10:00:00+00:00"})

    assert when == RecordedTime(_at("2026-07-27T10:00:00+00:00"),
                                _at("2026-07-27T10:00:00+00:00"))


def test_a_bare_date_pins_a_day_not_midnight():
    """The HIGH-1 defect, pinned. `changelog` entries written before this iterate
    carry only a date, and midnight is an instant the record never claimed."""
    when = entry_wall_time({"run_id": "r", "date": "2026-06-13", "version": "v0.26.0"})

    assert when is not None
    assert when.earliest == _at("2026-06-13T00:00:00+00:00")
    assert when.latest > _at("2026-06-13T23:59:59+00:00")
    assert when.latest < _at("2026-06-14T00:00:00+00:00")


def test_a_full_timestamp_in_the_date_key_is_still_an_instant():
    """The iterate ledger stamps a full instant under `date`. The shape is read
    from the VALUE, never from which key carried it."""
    when = entry_wall_time({"run_id": "r", "date": "2026-07-27T08:30:49.435429Z"})

    assert when is not None and when.earliest == when.latest


def test_a_naive_timestamp_is_read_as_utc():
    when = entry_wall_time({"at": "2026-07-27T10:00:00"})

    assert when is not None and when.earliest.tzinfo is not None
    assert when.earliest.utcoffset() == timezone.utc.utcoffset(None)


def test_at_wins_over_date_when_both_are_present():
    when = entry_wall_time({"at": "2026-07-27T10:00:00+00:00", "date": "2020-01-01"})

    assert when is not None and when.earliest.year == 2026


# --- event_at is the clock the marker can actually be compared to -------------

def test_event_at_wins_over_every_other_key():
    """`at` is wall clock; `event_at` is the newest-event time, the same value
    the canon marker stamps. Only the second is comparable with the marker, so
    it must win even though `at` is present on every entry the writer emits."""
    when = entry_anchor({
        "run_id": "r",
        "event_at": "2026-07-27T10:00:00+00:00",
        "at": "2026-07-27T12:00:00+00:00",
        "date": "2026-07-27",
    })

    assert when is not None and when.earliest == _at("2026-07-27T10:00:00+00:00")


def test_the_anchor_never_falls_back_to_a_wall_clock_key():
    """The two accessors are deliberately NOT one "best time" function.

    An anchor-preferring-with-fallback accessor existed, nothing consumed it,
    and its mere presence invited the cross-clock comparison that has broken
    this check twice. `entry_anchor`'s absence is the SIGNAL that the clock
    cannot be consulted — it must never be smoothed over by an `at`.
    """
    wall_only = {"at": "2026-07-27T10:00:00+00:00", "date": "2026-07-27"}

    assert entry_anchor(wall_only) is None
    assert entry_wall_time(wall_only) is not None
    assert entry_anchor({"event_at": "2026-07-27T10:00:00+00:00"}) is not None


def test_a_broken_event_at_is_no_anchor_even_beside_a_good_wall_clock():
    """It must NOT quietly borrow the `at` — that would be the cross-clock
    comparison, reached through a malformed record instead of a design error."""
    entry = {"event_at": 1753612800, "at": "2026-07-27T10:00:00+00:00"}

    assert entry_anchor(entry) is None
    assert entry_wall_time(entry) is not None


def test_the_wall_clock_reader_takes_the_first_key_that_PARSES():
    """Not the first that EXISTS: chaining with `or` let a present-but-broken
    `at` void an entry carrying a perfectly good `date` — a stated-unknown where
    a correct answer was on disk."""
    when = entry_wall_time({"at": "nonsense", "date": "2026-06-13"})

    assert when is not None and when.earliest == _at("2026-06-13T00:00:00+00:00")


# --- after() answers, or says it cannot ---------------------------------------

def test_an_instant_before_the_question_is_not_after():
    assert entry_anchor({"event_at": "2026-07-27T10:00:00+00:00"}).after(
        _at("2026-07-27T12:00:00+00:00")) is False


def test_an_instant_after_the_question_is_after():
    assert entry_anchor({"event_at": "2026-07-27T12:00:00+00:00"}).after(
        _at("2026-07-27T10:00:00+00:00")) is True


def test_an_exact_tie_is_not_after():
    """STRICT, and load-bearing. A completion recorded at the same anchor as the
    note was recorded by the canon block that WROTE the note — the marker and the
    completion read one clock a moment apart. Treating that tie as "later" is
    what accused every phase re-run of skipping its own C3 step."""
    assert entry_anchor({"event_at": "2026-07-27T10:00:00+00:00"}).after(
        _at("2026-07-27T10:00:00+00:00")) is False


def test_a_day_that_ends_before_the_question_answers_false():
    """A bare date is not useless: across days it still settles the order."""
    assert entry_wall_time({"date": "2026-06-13"}).after(
        _at("2026-07-27T10:00:00+00:00")) is False


def test_a_day_that_starts_after_the_question_answers_true():
    assert entry_wall_time({"date": "2026-07-28"}).after(
        _at("2026-07-27T10:00:00+00:00")) is True


def test_a_question_inside_the_recorded_day_is_unanswerable():
    """The case midnight used to answer with total confidence."""
    assert entry_wall_time({"date": "2026-07-27"}).after(
        _at("2026-07-27T10:00:00+00:00")) is None


# --- unusable input is None, never a guess ------------------------------------

def test_an_unparseable_timestamp_is_none():
    assert entry_wall_time({"at": "not-a-date"}) is None


def test_a_missing_timestamp_is_none():
    assert entry_wall_time({"run_id": "r"}) is None


def test_a_non_string_timestamp_is_none():
    assert entry_wall_time({"at": 1753612800}) is None

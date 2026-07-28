"""When did a phase last complete — answered to the precision the record carries.

Every phase records its completions somewhere, and Canon C3 joins the handoff's
canon marker against that record to answer "did THIS phase leave the handover
note" (iterate-2026-07-27-c3-phase-history-join). This module owns the reading
and the timekeeping; nothing here decides a verdict.

**Two records, because the pipeline has two.** Seven phases append to
``shipwright_run_config.json::phase_history``. ``iterate`` does not and never
has: its ledger is file-per-run under ``.shipwright/agent_docs/iterates/``,
because a shared array made two parallel iterates a guaranteed merge conflict.
``COMPLETION_PRODUCER`` names both, so a caller asks for a phase's completions
and gets them.

**One clock, or none.** The value C3 compares a completion against is the canon
marker's ``timestamp``, and that is NOT a wall clock: ``generate_session_handoff``
stamps ``latest_event_dt`` — the newest ts in ``shipwright_events.jsonl`` — because
``datetime.now()`` there re-dirtied the tracked handoff on every regeneration.
So a completion's own wall-clock ``at`` is *not* comparable with it: every canon
block records the event, writes the marker, then appends, which makes ``at``
unconditionally later than the marker that closed it. Comparing the two produced
a false "you skipped your step" on any phase re-run where ``record_event``'s
first-wins dedup meant no fresh event landed. ``append_phase_history`` therefore
also stamps ``event_at`` from the SAME function, and :func:`entry_anchor` reads
that key ALONE — never falling back, because the fallback is the mixed clock.

**Timestamps are read, never invented.** ``at``/``date`` are the wall clock, for
ordering two PHASES against each other (:func:`entry_wall_time`); ``date`` is a
bare ``YYYY-MM-DD`` on entries written before this iterate. A bare day is NOT an
instant, and reading it as midnight UTC is how the comparison died the first
time. So :class:`RecordedTime` carries the span the record actually pins down and
answers ``None`` when it cannot settle a question — never smoothed into a
default, because the guess would be a verdict about whether a phase did its job
(external plan review, openai R2).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .atomic_write import durable_read_text
from .iterate_entry import read_iterate_entries

#: The phase whose completions live in the iterate ledger, not ``phase_history``.
#: Named once, so the dispatch and the drift test read one constant.
ITERATE_PHASE = "iterate"

#: Which tool appends a completion for each phase. A phase C3 checks with no
#: producer here can only ever WARN, naming the wrong tool — which is what
#: ``iterate`` did after iterate-2026-07-27-c3-phase-content-key;
#: ``test_every_c3_phase_has_a_completion_producer`` now fails the build instead.
#: KNOWN BOUND — ``iterate``'s producer stamps no ``event_at``, so C3's clock
#: check never runs for it. Safe because its ledger is one FILE per run id: a
#: stale marker names a DIFFERENT run, which the run-id branch catches. Deferred
#: rather than dropped (trg-1346abbd) — the stamp would push a grandfathered file
#: past its bloat baseline for one out-of-band case.
COMPLETION_PRODUCER: dict[str, str] = {
    "project": "append_phase_history.py",
    "design": "append_phase_history.py",
    "plan": "append_phase_history.py",
    "build": "append_phase_history.py",
    "test": "append_phase_history.py",
    "changelog": "append_phase_history.py",
    "deploy": "append_phase_history.py",
    ITERATE_PHASE: "append_iterate_entry.py",
}

#: A timestamp that pins a day and no more. Matched against the RAW text:
#: ``datetime.fromisoformat("2026-06-13")`` yields midnight, and midnight is
#: exactly the instant the record does not claim.
_DATE_ONLY_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")

_ONE_DAY = timedelta(days=1)
_ONE_TICK = timedelta(microseconds=1)


def parse_iso_utc(text: str) -> datetime | None:
    """An ISO-8601 string as a tz-aware UTC datetime, or ``None``.

    Naive input is read as UTC — every producer in this repo stamps UTC, and the
    alternative (local time) would silently shift a comparison by the offset.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class RecordedTime:
    """When something happened, bounded by what the record actually states.

    An instant pins ``earliest == latest``. A bare date pins only the day it
    names, so the bounds span it and questions about that day are answered
    ``None`` rather than guessed. Both bounds are INCLUSIVE.
    """

    earliest: datetime
    latest: datetime

    def after(self, moment: datetime) -> bool | None:
        """Strictly after ``moment``? ``None`` when the span straddles it.

        STRICT, and only sound where equality means "same canon block": the
        marker and the completion it closes read one clock a moment apart, so
        equality is the shape of a correct run, not of a missing write. Do NOT
        reach for this to order two DIFFERENT phases — see :meth:`later_than`.
        """
        if self.earliest > moment:
            return True
        if self.latest <= moment:
            return False
        return None

    def later_than(self, other: RecordedTime) -> bool | None:
        """Is this span ENTIRELY after ``other``? ``None`` when the two overlap.

        For ordering two records against each other rather than a record against
        an instant. Equality is ``None``, not ``False``: two spans that coincide
        cannot be ordered, and the caller must say so instead of picking one.
        That is the difference from :meth:`after`, and it is load-bearing —
        ordering two phases by the marker's anchor read them as equal whenever
        ``record_event``'s permanent dedup denied the later phase a fresh event,
        and the check then announced the later phase had been superseded by the
        earlier one.
        """
        if self.earliest > other.latest:
            return True
        if self.latest < other.earliest:
            return False
        return None


@dataclass(frozen=True)
class PhaseCompletion:
    """The most recent recorded completion of one phase, on TWO separate clocks.

    Deliberately two fields rather than one "best" time, because the two
    questions C3 asks need different clocks and mixing them is the defect this
    class exists to prevent. There is no anchor-preferring convenience accessor:
    one existed, nothing consumed it, and its very existence invited exactly the
    cross-clock comparison that has broken this check twice.

    * :attr:`anchor` — the EVENT anchor, comparable with a canon marker's
      ``timestamp`` and with nothing else. ``None`` when the entry carries no
      ``event_at``, which is the signal that the clock cannot be consulted at
      all — NOT a count of entries.
    * :attr:`wall` — the wall clock, comparable with ANOTHER phase's ``wall``
      (one producer, one ``datetime.now()`` family) and with nothing else.
    """

    run_id: str
    #: Every run id recorded for this phase, oldest first, for membership tests.
    known_run_ids: tuple[str, ...] = ()
    wall: RecordedTime | None = None
    anchor: RecordedTime | None = None
    #: True when the entry CLAIMS an anchor (``event_at`` present), parsed or
    #: not. Absent and unreadable are different states: no key is a pre-
    #: ``event_at`` entry, where the run id is legitimately the whole answer;
    #: an unreadable key is a malformed record, and taking the run-id fallback
    #: there would disable the check on the input least deserving of trust.
    claims_anchor: bool = False


def entry_anchor(entry: dict[str, Any]) -> RecordedTime | None:
    """The entry's EVENT anchor, or ``None`` when it carries none.

    Never falls back to a wall-clock key. C3 consults the clock
    only where a real anchor exists, because only then are the marker and the
    completion on one clock; an entry written before ``event_at`` existed gets
    the run-id answer alone rather than a comparison across two clocks.
    """
    return recorded_time(entry.get("event_at"))


def entry_wall_time(entry: dict[str, Any]) -> RecordedTime | None:
    """The completion's WALL-clock time — never the event anchor.

    Two phases are ordered against each other on this, because both come from
    one producer calling ``datetime.now()`` and are therefore mutually
    comparable. The event anchor is not: ``record_event`` dedups
    ``phase_completed`` on ``(phase, splitId)`` permanently, so a phase
    completing a second time inherits whatever anchor was newest — routinely the
    anchor of some OTHER phase's canon block. Ordering two phases by that read
    them as simultaneous and announced the later one as superseded by the
    earlier.
    """
    for key in ("at", "date"):
        parsed = recorded_time(entry.get(key))
        if parsed is not None:
            return parsed
    return None


def recorded_time(raw: Any) -> RecordedTime | None:
    """One timestamp string as the span it actually pins down, or ``None``."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    parsed = parse_iso_utc(text)
    if parsed is None:
        return None
    if _DATE_ONLY_RE.match(text):
        return RecordedTime(parsed, parsed + _ONE_DAY - _ONE_TICK)
    return RecordedTime(parsed, parsed)


def _read_run_config(project_root: Path) -> dict[str, Any]:
    """Read the run config the way its own writer reads it.

    ``durable_read_text`` because a concurrent ``append_phase_history`` publish
    leaves the entry delete-pending on Windows and a plain ``open()`` fails —
    C3 runs from a Stop hook, concurrently with the phase skills that write this
    file, so a plain read turns a neighbour's in-flight write into "no completion
    recorded", a confident false claim with an unfollowable remedy.
    ``utf-8-sig`` because a hand-edit saved from Notepad carries a BOM, which
    ``json.loads`` rejects at char 0 (``lib/config.py`` BOM-hardened the sibling
    config readers for exactly this).
    """
    path = Path(project_root) / "shipwright_run_config.json"
    try:
        data = json.loads(durable_read_text(path, encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _recorded_entries(project_root: Path, phase: str) -> list[dict[str, Any]]:
    """Every recorded completion of ``phase``, oldest first.

    Order is the record's own: ``append_phase_history`` appends, and the iterate
    ledger's reader sorts by (timestamp, run_id). Re-sorting ``phase_history`` by
    timestamp here would reorder the day-precision entries written before this
    iterate, several of which share a day.

    So "latest" is POSITIONAL, and that rests on one assumption worth naming:
    nothing silently reorders the bucket. ``shipwright_run_config.json`` is not
    in ``.gitattributes``' union-merge set (only ``shipwright_events.jsonl`` and
    ``.shipwright/triage.jsonl`` are), so a concurrent append conflicts loudly
    rather than interleaving. A hand-edit that reorders entries after resolving
    such a conflict would defeat this, and no check would notice.
    """
    if phase == ITERATE_PHASE:
        return read_iterate_entries(Path(project_root))
    history = _read_run_config(project_root).get("phase_history")
    if not isinstance(history, dict):
        return []
    entries = history.get(phase)
    return entries if isinstance(entries, list) else []


def latest_completion(
    project_root: Path, phase: str, *, run_id: str = "",
) -> PhaseCompletion | None:
    """The most recent recorded completion of ``phase``, or ``None`` when absent.

    ``run_id`` narrows it to the latest completion recorded UNDER THAT RUN. C3
    uses it for the phase that wrote the note: that phase's own LATEST completion
    may be newer than the one the note closed, and treating it as a proxy for
    "when the note was written" excuses a phase that skipped its step — the
    silent-SKIP direction. ``known_run_ids`` still spans every entry, so
    membership answers do not change with the filter.
    """
    counted = [
        entry for entry in _recorded_entries(project_root, phase)
        if isinstance(entry, dict) and isinstance(entry.get("run_id"), str) and entry["run_id"]
    ]
    if not counted:
        return None
    matching = [e for e in counted if e["run_id"] == run_id] if run_id else counted
    if not matching:
        return None
    return PhaseCompletion(
        run_id=str(matching[-1]["run_id"]),
        known_run_ids=tuple(str(entry["run_id"]) for entry in counted),
        wall=entry_wall_time(matching[-1]),
        anchor=entry_anchor(matching[-1]),
        claims_anchor="event_at" in matching[-1],
    )


__all__ = [
    "COMPLETION_PRODUCER",
    "ITERATE_PHASE",
    "PhaseCompletion",
    "RecordedTime",
    "entry_anchor",
    "entry_wall_time",
    "latest_completion",
    "parse_iso_utc",
    "recorded_time",
]

"""Reading the event log for the FR change-history query (campaign S7).

The read layer, split from ``fr_change_history`` so neither module crosses the
size limit: this one knows how records are stored, ordered and amended;
``fr_change_history`` knows what question is being asked. Extracted per the
bloat-extraction recipe (cohesive cluster to a new module) rather than
ratcheting a baseline entry upward.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from lib.events_log import resolve_events_path
from lib.jsonl_records import read_jsonl_records


class EventLogUnreadable(RuntimeError):
    """The event log is present but could not be read or decoded.

    Distinct from "absent" (an ordinary state) and from "one record is corrupt"
    (recoverable, counted, reported). Raised rather than degraded because a
    silent empty answer here claims that nothing touched the requirement, over
    a log nobody managed to open.
    """


def sort_key(event: dict) -> tuple:
    """Order by *instant*, then event id for a stable tie-break.

    Timestamps are compared as ``datetime`` rather than as strings: the log
    permits non-UTC offsets, so an event written ``08:00+02:00`` must lose to a
    ``07:30Z`` one — lexicographic byte order gets that backwards. An
    unparseable or missing ``ts`` sorts last rather than raising; it is still
    reported, because dropping a record from an audit trail to keep a sort
    total is the trade this campaign exists to stop making.

    The event-id tie-break makes the order TOTAL: same-second appends are
    common on this log, and without it two runs of the same query could
    disagree.
    """
    raw = event.get("ts")
    parsed: datetime | None = None
    if isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        else:
            parsed = (
                parsed.replace(tzinfo=timezone.utc)
                if parsed.tzinfo is None
                else parsed.astimezone(timezone.utc)
            )
    return (
        parsed is None,
        parsed or datetime.min.replace(tzinfo=timezone.utc),
        str(event.get("id") or ""),
    )


def apply_amendments(events: list[dict]) -> list[dict]:
    """Fold ``event_amended`` records into their targets.

    An amendment can add or remove an FR link, so a reader that skipped this
    would answer from superseded data — 26 amendments are live in this repo's
    log today. Deliberately the same rule as the compliance collector's
    ``collectors.change_history._apply_amendments``; the two are pinned to the
    same answer by ``integration-tests/test_fr_history_amendment_parity.py``,
    because a reader that folded amendments differently from the RTM would make
    the two artifacts disagree about what happened.
    """
    amendments = {
        e["amends"]: e.get("fields", {})
        for e in events
        if e.get("type") == "event_amended" and e.get("amends")
    }
    out: list[dict] = []
    for e in events:
        if e.get("type") == "event_amended":
            continue
        if e.get("id") in amendments:
            e = {**e, **amendments[e["id"]]}
        out.append(e)
    return out


def read_work_events(project_root: Path | str) -> tuple[list[dict], int]:
    """Every ``work_completed`` event with amendments applied, plus a fragment count.

    Records are read through ``lib.jsonl_records`` rather than line-at-a-time:
    ``shipwright_events.jsonl`` carries ``merge=union`` and union merge is
    line-based, so an ordinary merge can join two records onto one physical
    line. A naive parse discards every record on such a line, which on an
    append-only audit trail turns a change that happened into one that never
    did (iterate-2026-07-19-…-readers). The same reader tolerates a partially
    written trailing record — this log is appended to while it is being read,
    including by the campaign that produced this module.

    The fragment count is RETURNED rather than logged and forgotten. A caller
    that cannot distinguish "no such change" from "the record was unreadable"
    is making the mistake this whole campaign is about.

    Raises
    ------
    :class:`EventLogUnreadable`
        The log exists but could not be read — permissions, a Windows share
        lock, or bytes that are not decodable as text. This deliberately does
        NOT degrade to an empty list: "the log could not be read" and "nothing
        touched this requirement" would then render identically, as
        ``No recorded changes.`` with exit 0 and no warning. That is the same
        swallow the fragment counting exists to remove, one layer up, and on an
        audit trail it is the more dangerous of the two because it hides
        *everything* rather than one record.

        A MISSING log is different and still returns empty: a project with no
        recorded changes is an ordinary state, not a fault.

    Notes
    -----
    Undecodable BYTES do not reach here as an exception and need no handler.
    External review proposed catching ``UnicodeDecodeError`` on the grounds that
    it is a ``ValueError`` and would slip past the ``OSError`` arm — correct
    about the type hierarchy, but the premise is false: ``read_jsonl_records``
    opens with ``errors="surrogateescape"``, so invalid UTF-8 degrades to a
    ``corrupt`` fragment and is reported through the count this function already
    returns. A handler for it was written, and then removed once probed: it was
    unreachable, and its test passed by never raising anything at all.
    ``test_undecodable_bytes_surface_as_a_fragment_not_an_exception`` pins the
    real behaviour so the question does not get re-litigated from the type
    hierarchy alone.
    """
    path = resolve_events_path(project_root)
    if not path.exists():
        return [], 0
    try:
        result = read_jsonl_records(path)
    except OSError as exc:
        raise EventLogUnreadable(
            f"the event log at {path} exists but could not be read: {exc}"
        ) from exc
    events = [
        e for e in apply_amendments(list(result.records))
        if e.get("type") == "work_completed"
    ]
    return events, len(result.corrupt)

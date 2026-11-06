"""The ONE assembling event-log reader (issue 978, campaign unit S2).

``read_events_assembled(root)`` returns every event of a tree as one ordered list:

1. the legacy ``shipwright_events.jsonl`` in FILE order (byte-for-byte what the
   plain legacy read gave -- a tree without the folders below is untouched), then
2. the archive (``shipwright_events.archive/``) and drop files
   (``shipwright_events.d/``) merged and sorted by (parsed instant, id). Ties on both keep
   folder (archive, then drops), file-name, then in-file order, so the result is deterministic.

Layout independent: the folders are read whenever they exist, whatever
``events_layout`` says -- a reader must see what any writer, old or new, left.

PER-FILE STATUS (:class:`FileStatus`): ``ok`` (records, nothing left over),
``corrupt`` (an unrecoverable remainder; the records around it ARE still returned,
recovery is the shared ``split_records`` one), ``empty`` (no record, nothing else)
and ``unreadable`` (``OSError``). Status means "something is wrong with this file",
never "the file is unusable". Every caller keeps its own policy:

* gates that conclude an event is ABSENT call :meth:`AssembledRead.absence_blockers`
  with the run's key and refuse to conclude when it is non-empty -- ONLY a non-ok
  DROP file named for that key blocks (kill criterion 8). A damaged legacy or archive
  file, or another run's drop, is tolerated and merely counted;
* batch readers (compliance, dashboards) skip and report ``skipped_files``;
* ``events_log.finalized_run_ids`` keeps answering "unknown" (``None``) on unreadable.

Archive/drop duplicates (a fold racing a fold writes the same event twice): an
identical id with identical content collapses to one record, an identical id with
different content keeps BOTH and lists the id in ``duplicate_ids``. The legacy file
is never deduplicated.

Stdlib + sibling imports only; package-member context (``lib.events_read``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .events_log import ARCHIVE_DIR, event_files, resolve_events_path
from .jsonl_records import RecordRead, read_jsonl_records

KEY_MAX = 80
_BAD_KEY_CHARS = re.compile(r"[^A-Za-z0-9._-]")
#: ``<key>--<wt8>--<nonce8>.jsonl`` -- the drop name written by ``events_layout``.
_DROP_NAME = re.compile(r"^(?P<key>.+)--[0-9a-f]{8}--[0-9a-f]{8}\.jsonl$")


def sanitize_key(raw: str) -> str:
    """Make ``raw`` a path-safe key (``[A-Za-z0-9._-]``, 1..80). Never empty."""
    key = _BAD_KEY_CHARS.sub("-", raw).lstrip(".") or "_run"
    return key[:KEY_MAX]


@dataclass(frozen=True)
class FileStatus:
    """What reading ONE event file found."""

    path: str
    kind: str  # "legacy" | "archive" | "drop"
    key: str | None  # the run key of a drop (None for legacy/archive/odd names)
    status: str  # "ok" | "corrupt" | "empty" | "unreadable"
    records: int = 0
    fragments: int = 0


@dataclass
class AssembledRead(RecordRead):
    """``RecordRead`` (records + corrupt fragments) plus per-file status."""

    files: list[FileStatus] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)

    @property
    def skipped_files(self) -> list[FileStatus]:
        """Every non-ok file (batch readers report the count)."""
        return [f for f in self.files if f.status != "ok"]

    def absence_blockers(self, run_key: str) -> list[FileStatus]:
        """Non-ok DROP files of ``run_key`` -- a gate must not conclude "absent".

        ``run_key`` is normalised exactly as the writer names its files, so a run id
        longer than 80 characters or with unusual characters still matches its own files.
        Callers pass the key the WRITER used (``events_layout.drop_key``: the run id, or
        ``_branch-<slug>`` / ``_main`` when none was set), not a free-form id.
        A non-ok drop whose name does not follow the writer's shape (``key is None``)
        cannot be ruled out as the run's, so it blocks too (fail closed).
        """
        key = sanitize_key(run_key)
        return [f for f in self.files if f.kind == "drop" and f.status != "ok" and f.key in (key, None)]


class EventLogNotReadable(RuntimeError):
    """An absence gate cannot decide: a drop file of the run's key is non-ok."""


def require_readable_for_absence(read: AssembledRead, run_key: str) -> None:
    """Raise :class:`EventLogNotReadable` when ``run_key``'s own drop files are damaged."""
    bad = read.absence_blockers(run_key)
    if bad:
        raise EventLogNotReadable(
            f"event drop file(s) of run {run_key!r} are not ok, so the absence of an event "
            "cannot be concluded: " + ", ".join(f"{Path(f.path).name} ({f.status})" for f in bad))


def instant(ts: object) -> datetime:
    """Parsed UTC instant; unparseable sorts first (a total order is all we need)."""
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def latest_by_ts(events: Iterable[Any], predicate=None) -> Any | None:
    """The event with the newest parsed ``ts`` (ties: the later position), or ``None``.

    The position-reader replacement: "the last event" must mean the newest one, not
    whatever happens to sit last in the file or the assembled list.
    """
    best, best_key = None, None
    for index, event in enumerate(events):
        if not isinstance(event, dict) or (predicate is not None and not predicate(event)):
            continue
        key = (instant(event.get("ts")), index)
        if best_key is None or key >= best_key:
            best, best_key = event, key
    return best


def sorted_by_ts(events: Iterable[Any]) -> list[Any]:
    """Events oldest to newest by parsed ``ts``; ties keep list position (stable)."""
    return sorted(events, key=lambda e: instant(e.get("ts")) if isinstance(e, dict) else instant(None))


def _status(records: list[dict], fragments: int, kind: str) -> str:
    if fragments:
        return "corrupt"
    # A zero-record legacy file is a legitimate state (after a full fold); an empty
    # archive/drop file is not (files are only created by a complete first write).
    return "ok" if records or kind == "legacy" else "empty"


def _read_one(path: Path, kind: str) -> tuple[RecordRead, FileStatus] | None:
    match = _DROP_NAME.match(path.name) if kind == "drop" else None
    key = match.group("key") if match else None
    try:
        part = read_jsonl_records(path)
    except OSError as exc:
        if kind == "legacy":
            raise  # unchanged: an unreadable legacy log never reads as "no events"
        if isinstance(exc, FileNotFoundError):
            return None  # deleted between the existence check and the open (a fold)
        return RecordRead(), FileStatus(str(path), kind, key, "unreadable")
    return part, FileStatus(str(path), kind, key, _status(part.records, len(part.corrupt), kind),
                            len(part.records), len(part.corrupt))


def _canonical(event: dict) -> str:
    """Content identity of an event; the stamped ``run`` field is not content (DESIGN 10.2)."""
    event = {k: v for k, v in event.items() if k != "run"}
    return json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _dedup_extra(extra: list[dict]) -> tuple[list[dict], list[str]]:
    seen: dict[str, set[str]] = {}
    kept: list[dict] = []
    flagged: list[str] = []
    for event in extra:
        ident = event.get("id")
        if not isinstance(ident, str) or not ident:
            kept.append(event)
            continue
        body = _canonical(event)
        bodies = seen.setdefault(ident, set())
        if body in bodies:
            continue  # same id, same content: the fold-race duplicate
        if bodies and ident not in flagged:
            flagged.append(ident)  # same id, different content: keep both, flag
        bodies.add(body)
        kept.append(event)
    return kept, flagged


def read_events_assembled(project_root: Path | str) -> AssembledRead:
    """Legacy file in FILE order, then archive + drops by (parsed instant, id)."""
    root = Path(project_root)
    legacy_path = resolve_events_path(root)
    result = AssembledRead()
    extra: list[dict] = []
    for path in event_files(root):
        if path == legacy_path:
            if not path.exists():
                continue
            kind = "legacy"
        elif not path.exists():
            continue  # deleted between listing and reading (a fold, a checkout)
        else:
            kind = "archive" if path.parent.name == ARCHIVE_DIR else "drop"
        one = _read_one(path, kind)
        if one is None:
            continue
        part, status = one
        result.files.append(status)
        result.corrupt.extend(part.corrupt)
        (result.records if kind == "legacy" else extra).extend(part.records)
    if extra:
        extra.sort(key=lambda e: (instant(e.get("ts")), str(e.get("id", ""))))
        extra, result.duplicate_ids = _dedup_extra(extra)
        result.records.extend(extra)
    return result


__all__ = [
    "AssembledRead", "EventLogNotReadable", "FileStatus", "instant",
    "latest_by_ts", "read_events_assembled", "sanitize_key", "sorted_by_ts", "require_readable_for_absence",
]

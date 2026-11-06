"""The ONE event writer module (issue 978, campaign unit S4).

Every appender of the event log (``record_event``, the adopt seeder, the config
converter, the F5b/F7 writers) goes through here. FORMAT CHANGES ARE DROPS-ONLY:

* ``legacy`` (the default): ``write_event_line`` writes exactly the bytes the old inline
  code wrote -- termination guard, one line, ``fsync``; no ``run`` field, 8-hex ids.
* ``drops``: the event is stamped with ``run`` (the key :func:`events_layout.drop_key` chose),
  ids are 16 hex, the open drop of the run's key is appended to (rotate-on-commit lives in
  ``events_layout``), and a drop file is CREATED atomically -- written to a hidden temp name
  and renamed -- so a crash can never leave an empty ``*.jsonl`` that would block the run's
  absence gates (kill criterion 8). A repeated event (same id, same content) is dropped.

Callers hold ``events_lock_path``'s lock around :func:`write_event_line`; the dedup scans
that decide WHETHER to write run under the same lock, over the whole assembled log.
"""

from __future__ import annotations

import json
import os
from datetime import timedelta, timezone, datetime
from pathlib import Path
from uuid import uuid4

from .config import read_events
from .events_layout import drop_key, events_layout, events_lock_path, resolve_events_write_path
from .events_read import read_events_assembled, require_readable_for_absence
from .file_lock import FileLock
from .events_log import DROPS_DIR, event_files
from .events_read import instant
from .jsonl_records import ends_without_newline, read_jsonl_records


def new_event_id(project_root: Path | str | None = None) -> str:
    """``evt-`` + 8 hex under legacy (unchanged), 16 hex under the drops layout."""
    width = 16 if project_root is not None and events_layout(project_root) == "drops" else 8
    return f"evt-{uuid4().hex[:width]}"


def stamp_run(event: dict, project_root: Path | str, run_id: str | None = None) -> dict:
    """Drops only: stamp the key the writer will use into ``event['run']``. Legacy: untouched."""
    if events_layout(project_root) == "drops":
        event["run"] = drop_key(project_root, None, run_id)
    return event


def _same_content(a: dict, b: dict) -> bool:
    strip = lambda e: {k: v for k, v in e.items() if k != "run"}  # noqa: E731 -- run is not content
    return json.dumps(strip(a), sort_keys=True, default=str) == json.dumps(strip(b), sort_keys=True, default=str)


def _already_in(path: Path, event: dict) -> bool:
    ident = event.get("id")
    if not ident or not path.exists():
        return False
    return any(r.get("id") == ident and _same_content(r, event) for r in read_jsonl_records(path).records)


def _already_anywhere(root: Path, chosen: Path, event: dict) -> bool:
    """The same id with the same content in ANY other drop (the original may have been closed by a commit)."""
    return bool(event.get("id")) and any(p != chosen and _already_in(p, event) for p in event_files(root)[1:])


def _monotonic_ts(path: Path, event: dict) -> None:
    """Drops: a later append never carries an earlier-or-equal ``ts`` than the file's last record.

    Readers order drops by parsed instant (then id), so on a coarse clock (Windows ticks) two events of
    one writer would tie and be scrambled by their random ids. Bumping by whole microseconds keeps the
    file order == time order for a single writer; it never moves an event more than a few ticks.
    """
    if not path.exists() or not isinstance(event.get("ts"), str):
        return
    records = read_jsonl_records(path).records
    last = max((instant(r.get("ts")) for r in records), default=None)
    if last is not None and instant(event["ts"]) <= last:
        event["ts"] = (last + timedelta(microseconds=1)).isoformat()


def require_run_drops_readable(project_root: Path | str, run_id: str | None = None) -> None:
    """Drops layout: an "absent" verdict needs this run's own drop files readable (KC8); raises EventLogNotReadable."""
    if events_layout(project_root) == "drops":
        require_readable_for_absence(read_events_assembled(project_root), drop_key(project_root, None, run_id))


def amend_commit(project_root: Path | str, event_id: str, commit_sha: str, run_id: str | None = None) -> bool:
    """Drops layout: record ``commit`` as an ``event_amended`` drop (a closed file is never edited).

    False when the target event is unknown. The key is the explicit ``run_id``, else the target's ``adr_id``.
    """
    with FileLock(events_lock_path(project_root)):
        target = next((e for e in read_events(project_root) if e.get("id") == event_id), None)
        if target is None:
            return False
        write_event_line(project_root, {
            "v": 1, "id": new_event_id(project_root), "ts": datetime.now(timezone.utc).isoformat(),
            "type": "event_amended", "amends": event_id, "fields": {"commit": commit_sha}},
            run_id or target.get("adr_id"))
    return True


def _create_atomically(path: Path, line: str) -> None:
    tmp = path.with_name("." + path.name + ".tmp")  # not ``*.jsonl``: invisible to every reader
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(line)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_event_line(project_root: Path | str, event: dict, run_id: str | None = None) -> Path | None:
    """Append ``event`` (CALLER HOLDS THE LOCK). Returns the file written, ``None`` for a repeat.

    Stamps ``run`` under the drops layout (``event`` is mutated, as the caller's copy of the
    record). Under legacy this is byte-identical to the former inline append.
    """
    root = Path(project_root)
    drops = events_layout(root) == "drops"
    if drops:
        stamp_run(event, root, run_id)
    path = resolve_events_write_path(root, run_id)
    if drops and (_already_in(path, event) or _already_anywhere(root, path, event)):
        return None
    if drops:
        _monotonic_ts(path, event)
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    if drops and not path.exists():
        (root / DROPS_DIR).mkdir(exist_ok=True)
        _create_atomically(path, line)
        return path
    needs_separator = ends_without_newline(path)
    with open(path, "a", encoding="utf-8", **({"newline": "\n"} if drops else {})) as fp:  # drops: LF on Windows too
        if needs_separator:
            fp.write("\n")
        fp.write(line)
        fp.flush()
        os.fsync(fp.fileno())
    return path


__all__ = ["amend_commit", "new_event_id", "require_run_drops_readable", "stamp_run", "write_event_line"]

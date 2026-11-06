"""Raw event lines and the log fingerprint for ``event_context_index`` (issue 978, S3).

The index is derived from the WHOLE event log, so its source is the assembled set
of files (legacy, then archive and drop files), not the one legacy path. A tree
without the folders is read exactly as before: physical line numbers are the
``sequence`` and the fingerprint is the sha256 of the legacy bytes, so a cached
index stays valid across this change. With folders, the extra files follow in
(parsed instant, id) order with the sequence continuing after the legacy lines, and
the fingerprint also covers each extra file's name and bytes.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Iterator

from .events_log import event_files
from .events_read import instant
from .jsonl_records import split_records


def _sort_key(raw: bytes) -> tuple:
    try:
        event = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        event = None
    event = event if isinstance(event, dict) else {}
    return instant(event.get("ts")), str(event.get("id", ""))


def _one_record_per_line(raw: bytes) -> list[bytes]:
    """A physical line holding several concatenated records becomes one line each (shared recovery)."""
    try:
        json.loads(raw.decode("utf-8"))
        return [raw]
    except (UnicodeError, ValueError):
        records, _remainder = split_records(raw.decode("utf-8", errors="replace"))
        return [json.dumps(r, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n" for r in records] or [raw]


def _extra_lines(files: list[Path]) -> list[bytes]:
    out: list[bytes] = []
    for path in files:
        try:
            data = path.read_bytes()
        except OSError:
            continue  # vanished or unreadable: the fingerprint below says so
        for raw in io.BytesIO(data):
            if raw.strip():
                out.extend(_one_record_per_line(raw))
    out.sort(key=_sort_key)
    return out


def iter_event_lines(project_root: Path | str) -> Iterator[tuple[int, bytes]]:
    """``(sequence, raw line)``: legacy lines by physical number, then the folders' lines."""
    files = event_files(project_root)
    sequence = 0
    if files[0].exists():
        with files[0].open("rb") as handle:
            for sequence, raw in enumerate(handle, start=1):
                yield sequence, raw
    for raw in _extra_lines(files[1:]):
        sequence += 1
        yield sequence, raw


def source_stats(project_root: Path | str) -> dict:
    """``{bytes, count, estimated_tokens, fingerprint}`` over the whole log."""
    files = event_files(project_root)
    if not any(p.exists() for p in files):
        return {"bytes": 0, "count": 0, "estimated_tokens": 0, "fingerprint": "missing"}
    digest, count, size = hashlib.sha256(), 0, 0
    try:
        for index, path in enumerate(files):
            if index and path.exists():
                digest.update(b"\0" + path.parent.name.encode() + b"/" + path.name.encode() + b"\0")
            if not path.exists():
                continue
            with path.open("rb") as handle:
                for raw in handle:
                    digest.update(raw)
                    size += len(raw)
                    count += 1 if raw.strip() else 0
    except OSError:
        return {"bytes": 0, "count": 0, "estimated_tokens": 0, "fingerprint": "unreadable"}
    return {"bytes": size, "count": count, "estimated_tokens": (size + 3) // 4,
            "fingerprint": digest.hexdigest()}

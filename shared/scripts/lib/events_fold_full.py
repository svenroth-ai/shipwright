"""Full fold: every archive and drop event back into the one legacy log (issue 978, S6; second rollback).

For consumers still on plugins from before the drops layout (they read only the single log file). One-time,
conflict-accepting -- a PR that was open against the drops carries stale paths. Steps, all under the events lock:

1. read the whole log through the assembling reader (``read_events_assembled``: legacy in file order, then
   archive and drops by instant and id) and scan it for ids -- the same id with DIFFERENT content in the legacy
   log and the folders stops the fold (``allow_conflicts`` appends both). An identical copy is simply skipped;
2. append the events the legacy log does not hold yet, one line each, after the log's termination guard;
3. delete the archive and drop files whose every event is now in the legacy log (files that are not ok stay and
   are reported -- their unrecoverable remainder would be lost), and set ``events_layout`` to ``legacy``.

The ``run`` stamp stays on appended lines (old readers ignore an unknown field). Events without an id are
appended unless an identical line exists. Idempotent: a second run finds nothing to append.
"""

from __future__ import annotations

import os
from pathlib import Path

from .events_fold import ensure_keep, set_layout
from .events_fold_io import content_hash, dump_line, parse_bytes
from .events_layout import events_lock_path
from .events_log import ARCHIVE_DIR, DROPS_DIR, event_files, resolve_events_path
from .events_read import read_events_assembled
from .file_lock import FileLock
from .jsonl_records import ends_without_newline


def plan_full_fold(root: Path | str) -> dict:
    """What a full fold would do: ``append`` (records), ``files`` (to delete), ``skipped``, ``conflicts``."""
    root = Path(root)
    legacy = resolve_events_path(root)
    in_legacy = parse_bytes(legacy.read_bytes()).records if legacy.exists() else []
    hashes = {content_hash(r) for r in in_legacy}
    by_id = {r["id"]: content_hash(r) for r in in_legacy if isinstance(r.get("id"), str)}
    read = read_events_assembled(root, include_legacy=False)
    append, conflicts, seen = [], [], set(hashes)
    for record in read.records:
        digest = content_hash(record)
        ident = record.get("id")
        if digest in seen:
            continue
        if isinstance(ident, str) and by_id.get(ident, digest) != digest and ident not in conflicts:
            conflicts.append(ident)
        seen.add(digest)
        append.append(record)
        if isinstance(ident, str):
            by_id.setdefault(ident, digest)
    ok = {f.path for f in read.files if f.status == "ok"}
    files = [p for p in event_files(root)[1:] if str(p) in ok]
    skipped = [{"file": Path(f.path).name, "reason": f.status} for f in read.files if f.status != "ok"]
    return {"append": append, "files": files, "skipped": skipped,
            "conflicts": sorted(set(conflicts) | set(read.duplicate_ids))}


def apply_full_fold(root: Path | str, *, allow_conflicts: bool = False) -> dict:
    root = Path(root)
    with FileLock(events_lock_path(root)):
        plan = plan_full_fold(root)
        if plan["conflicts"] and not allow_conflicts:
            return {"status": "conflict", "conflicting_ids": plan["conflicts"], "skipped": plan["skipped"]}
        legacy = resolve_events_path(root)
        lines = "".join(dump_line(r) + "\n" for r in plan["append"])
        if lines:
            separator = "\n" if ends_without_newline(legacy) else ""
            with open(legacy, "a", encoding="utf-8", newline="\n") as fp:
                fp.write(separator + lines)
                fp.flush()
                os.fsync(fp.fileno())
        held = {content_hash(r) for r in parse_bytes(legacy.read_bytes()).records}
        gone = []
        for path in plan["files"]:
            if all(content_hash(r) in held for r in parse_bytes(path.read_bytes()).records):
                path.unlink()
                gone.append(f"{path.parent.name}/{path.name}")
        ensure_keep(root)
        set_layout(root, "legacy")
    return {"status": "folded_into_legacy", "appended": len(plan["append"]), "removed_files": gone,
            "skipped": plan["skipped"], "legacy_log": legacy.relative_to(root).as_posix(), "folders": [DROPS_DIR, ARCHIVE_DIR]}

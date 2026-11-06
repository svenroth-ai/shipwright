"""Full fold: every archive and drop event back into the one legacy log (issue 978, S6; second rollback).

For consumers still on plugins from before the drops layout (they read only the single log file). One-time,
conflict-accepting -- a PR that was open against the drops carries stale paths. Steps, all under the events lock:

1. read the legacy log and every archive/drop file that is fully ok (a file with an unrecoverable remainder is
   reported and left alone, with its records: appending them would duplicate them for good) and scan for ids --
   the same id with DIFFERENT content in the legacy log and the folders stops the fold (``allow_conflicts``
   appends both). An identical copy is simply skipped; the rest is appended in the reader's order;
2. append the events the legacy log does not hold yet, one line each, after the log's termination guard;
3. delete those files once every event is verified in the legacy log, and set ``events_layout`` to ``legacy``.

The ``run`` stamp stays on appended lines (old readers ignore an unknown field). Events without an id are
appended unless an identical line exists. Idempotent: a second run finds nothing to append.
"""

from __future__ import annotations

import os
from pathlib import Path

from .events_fold import ensure_keep, read_sync_config, set_layout
from .events_fold_io import content_hash, dump_line, parse_bytes, sort_key
from .events_layout import events_lock_path
from .events_log import ARCHIVE_DIR, DROPS_DIR, event_files, resolve_events_path
from .file_lock import FileLock
from .jsonl_records import ends_without_newline


def plan_full_fold(root: Path | str) -> dict:
    """What a full fold would do: ``append`` (records), ``files`` (to delete), ``skipped``, ``conflicts``.

    Only files that are fully ok are taken: the recovered records of a corrupt file would be appended while the
    file stays behind, and every later assembled read would then see them twice.
    """
    root = Path(root)
    legacy = resolve_events_path(root)
    in_legacy = parse_bytes(legacy.read_bytes()).records if legacy.exists() else []
    by_id: dict[str, set[str]] = {}
    for r in in_legacy:
        if isinstance(r.get("id"), str):
            by_id.setdefault(r["id"], set()).add(content_hash(r))
    seen = {content_hash(r) for r in in_legacy}
    files, skipped, incoming = [], [], []
    for path in event_files(root)[1:]:
        parsed = parse_bytes(path.read_bytes())
        if parsed.status != "ok":
            skipped.append({"file": path.name, "reason": parsed.status})
            continue
        files.append(path)
        incoming += parsed.records
    append, conflicts = [], set()
    for record in sorted(incoming, key=sort_key):
        digest, ident = content_hash(record), record.get("id")
        if digest in seen:
            continue
        seen.add(digest)
        append.append(record)
        if isinstance(ident, str):
            if by_id.get(ident) and digest not in by_id[ident]:
                conflicts.add(ident)
            by_id.setdefault(ident, set()).add(digest)
    return {"append": append, "files": files, "skipped": skipped, "conflicts": sorted(conflicts)}


def apply_full_fold(root: Path | str, *, allow_conflicts: bool = False) -> dict:
    root = Path(root)
    read_sync_config(root)  # an unusable config must stop the rollback BEFORE a single file moves
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
        held = {content_hash(r) for r in parse_bytes(legacy.read_bytes() if legacy.exists() else b"").records}
        gone = []
        for path in plan["files"]:
            if all(content_hash(r) in held for r in parse_bytes(path.read_bytes()).records):
                path.unlink()
                gone.append(f"{path.parent.name}/{path.name}")
        ensure_keep(root)
        set_layout(root, "legacy")
    return {"status": "folded_into_legacy", "appended": len(plan["append"]), "removed_files": gone,
            "skipped": plan["skipped"], "legacy_log": legacy.relative_to(root).as_posix(), "folders": [DROPS_DIR, ARCHIVE_DIR]}

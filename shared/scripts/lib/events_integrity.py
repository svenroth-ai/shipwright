"""Integrity check of the event folders (issue 978, campaign unit S6, kill criterion 6).

Judged against the MERGE-BASE of a change: a PR may only ADD files under ``shipwright_events.d/``,
``shipwright_events.archive/`` and ``shipwright_events.quarantine/``. Anything that touches a file which
exists at the merge-base is a violation, except two recognised housekeeping shapes:

* **fold** -- a deleted DROP whose every event (equal per-event hash) is present in an archive file this
  change ADDS. The deleted file must hold at least one recoverable event.
* **quarantine** -- a deleted DROP that held ZERO recoverable events and was non-ok AT THE MERGE-BASE (re-derived
  here from the base blob, not taken from the change's word), moved byte-identically (same blob) into the
  quarantine folder.

``allow_full_fold`` (the operator's rollback commit) additionally accepts deleting archive/drop files whose
events are all in the legacy log at the head (compared without the ``run`` stamp, like the tool), and archive
files that hold events from drops this commit does not delete (an emergency fold of unmerged drops).
An added archive file otherwise may only hold events of drops the same change deletes (``archive_injection``).

Also blocked: a path that is not exactly one legal segment under its folder (traversal, nesting, hidden or
overlong key), an added entry that is not a regular file (symlink, submodule), and a FORGED run id -- an added
drop holding an event stamped with a ``run`` other than the file's own key, or (``own_keys`` given) a file under
a key the change does not own. Legacy-log appends are S7's consumer check, not this one.

No-op (no violations) while neither side has any of the folders. Blobs are read with ``git cat-file``.
Never prints.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .events_fold_io import (
    EMPTY_BLOB, FOLDERS, GitError, KEEP_NAME, blob, content_hash, drop_key_of, event_hash, git, name_problem, parse_bytes, tree_names,
)
from .events_log import ARCHIVE_DIR, DROPS_DIR, EVENT_FILE, QUARANTINE_DIR
from .events_read import sanitize_key

REGULAR_MODES = ("100644", "100755")
ARCHIVE_FOLD_NAME = re.compile(r"^fold-[0-9a-f]{12}\.jsonl\Z")


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    detail: str


@dataclass
class Entry:
    status: str
    old_mode: str
    new_mode: str
    old_sha: str
    new_sha: str
    path: str

    @property
    def folder(self) -> str:
        return self.path.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.path.split("/", 1)[1] if "/" in self.path else ""


def _entries(root: Path, base: str, head: str) -> list[Entry]:
    """Changed entries inside the event folders, plus case variants of a folder name (``Shipwright_Events.D/``).

    The whole tree is diffed and filtered here: a pathspec is case-sensitive on a Linux runner, while the same
    path lands INSIDE the real folder on a case-insensitive checkout (Windows, macOS) and is then read.
    """
    raw = git(root, "diff", "--raw", "-z", "--no-abbrev", "--no-renames", base, head).stdout
    parts = raw.decode("utf-8", errors="surrogateescape").split("\0")
    lowered = {f.lower() for f in FOLDERS}
    out = []
    for meta, path in zip(parts[0::2], parts[1::2]):
        first = path.split("/", 1)[0]
        fields = meta.lstrip(":").split()
        if len(fields) == 5 and first.lower() in lowered:
            out.append(Entry(fields[4][0], fields[0], fields[1], fields[2], fields[3], path))
    return out


def _base_archive_hashes(root: Path, base: str) -> set[str]:
    out: set[str] = set()
    for name in tree_names(root, base, ARCHIVE_DIR) or ():
        out |= {event_hash(r) for r in parse_bytes(blob(root, base, f"{ARCHIVE_DIR}/{name}") or b"").records}
    return out


def _covered(parsed_events: list[dict], pool: set[str]) -> bool:
    return bool(parsed_events) and all(event_hash(r) in pool for r in parsed_events)


def check_integrity(root: Path | str, base_ref: str, head_ref: str = "HEAD", *, own_keys: tuple[str, ...] = (),
                    allow_full_fold: bool = False) -> list[Violation]:
    """Every violation of the rules above for the change ``merge-base(base_ref, head_ref)`` .. ``head_ref``."""
    root = Path(root)
    base = git(root, "merge-base", base_ref, head_ref).stdout.decode().strip()
    head = git(root, "rev-parse", "--verify", f"{head_ref}^{{commit}}").stdout.decode().strip()
    entries = _entries(root, base, head)
    bad: list[Violation] = []

    def flag(code: str, e: Entry, detail: str) -> None:
        bad.append(Violation(code, e.path, detail))

    legacy_hashes: set[str] | None = None
    collisions: set[str] = set()
    if any(e.status == "A" and e.folder in (DROPS_DIR, ARCHIVE_DIR) for e in entries):  # case-insensitive checkouts merge such names
        for folder in (DROPS_DIR, ARCHIVE_DIR):
            seen = Counter(n.lower() for n in tree_names(root, head, folder) or ())
            collisions |= {n for n, c in seen.items() if c > 1}
    archives: list[tuple[Entry, list[dict]]] = []
    added_archive: set[str] = set()   # per-event hashes of archive files this change adds
    added_quarantine = {(e.new_sha, e.name): e for e in entries if e.status == "A" and e.folder == QUARANTINE_DIR}
    for e in entries:
        if e.folder not in FOLDERS:
            flag("bad_path", e, f"{e.folder!r} is a case variant of an event folder")
            continue
        if "/" not in e.path or e.path.count("/") != 1 or name_problem(e.folder, e.name):
            flag("bad_path", e, name_problem(e.folder, e.name) or "not a single segment under its folder")
            continue
        if e.status == "A":
            if e.new_mode not in REGULAR_MODES:
                flag("not_a_regular_file", e, f"mode {e.new_mode}")
                continue
            if e.name == KEEP_NAME:
                if e.new_sha != EMPTY_BLOB:
                    flag("bad_path", e, f"{KEEP_NAME} must be empty")
                continue
            data = blob(root, head, e.path)
            parsed = parse_bytes(data or b"")
            if e.folder == ARCHIVE_DIR:
                added_archive |= {event_hash(r) for r in parsed.records}
                archives.append((e, parsed.records))
                if not ARCHIVE_FOLD_NAME.match(e.name):
                    flag("bad_path", e, "an archive file is named fold-<12 hex>.jsonl")
            if e.folder == DROPS_DIR:
                key = drop_key_of(e.name)
                if own_keys and key not in own_keys:
                    flag("foreign_key", e, f"key {key!r} is not one of this change's run ids {list(own_keys)}")
                if any(r.get("run") != key or (r.get("type") == "work_completed" and sanitize_key(str(r.get("adr_id", key))) != key)
                       for r in parsed.records):
                    flag("forged_run_id", e, f"an event is not stamped with the file's own key {key!r} (run, or adr_id of a work_completed)")
                if e.name.lower() in collisions:
                    flag("case_collision", e, "differs only in letter case from another file in the folder")
    for e in entries:
        if e.status == "A" or any(v.path == e.path for v in bad):
            continue
        if e.status != "D":
            flag("modified_existing", e, "a file that exists at the merge-base may not be modified")
            continue
        old = parse_bytes(blob(root, base, e.path) or b"")
        if e.folder == DROPS_DIR and _covered(old.records, added_archive):
            continue  # fold: every deleted event is in an added archive file
        twin = added_quarantine.get((e.old_sha, e.name))
        if e.folder == DROPS_DIR and twin is not None and not old.records and old.status != "ok":
            continue  # quarantine: unrecoverable at the merge-base, moved byte-identically
        if allow_full_fold and e.folder in (DROPS_DIR, ARCHIVE_DIR):
            if legacy_hashes is None:
                legacy_hashes = {content_hash(x) for x in parse_bytes(blob(root, head, EVENT_FILE) or b"").records}
            if old.records and all(content_hash(r) in legacy_hashes for r in old.records):
                continue
        flag("deleted_existing", e, "deleted without a fold (events not all in an added archive) or quarantine twin")
    if not allow_full_fold:  # an added archive may hold only events that this change moves out of deleted merge-base drops
        deleted = {event_hash(r) for e in entries if e.status == "D" and e.folder == DROPS_DIR
                   for r in parse_bytes(blob(root, base, e.path) or b"").records}
        for e, records in archives:
            if any(event_hash(r) not in deleted for r in records):
                deleted |= _base_archive_hashes(root, base)  # an overlapping earlier fold already holds them (the reader dedups)
            if any(event_hash(r) not in deleted for r in records):
                flag("archive_injection", e, "holds events that no deleted merge-base drop held")
    return bad


__all__ = ["GitError", "Violation", "check_integrity"]

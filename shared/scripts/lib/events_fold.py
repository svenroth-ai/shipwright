"""Fold, emergency fold and quarantine of the per-run drop files (issue 978, campaign unit S6).

Housekeeping, not a daily actor. All three move EXISTING drop files, so they are the only legal
modify/delete of a file that exists at the merge-base (``events_integrity`` recognises them):

* **fold** -- drops that are on the base ref (merged), unmodified since, and whose every event is older than
  :data:`FOLD_AGE_DAYS` (by event ``ts``, never mtime) move into ONE new archive file
  ``shipwright_events.archive/fold-<hash>.jsonl`` and are deleted in the same change. The archive name is the
  hash of the folded set, so a second fold of the same set (concurrent, or a re-run) produces the same file
  (clean add/add) and a fold of nothing is a no-op. Files whose events are not all ok are left and reported.
* **emergency fold** -- the first rollback: every ok drop (age and merge state ignored) into the archive, and
  ``events_layout`` back to ``legacy``. Post-change readers keep seeing everything (archive is read).
* **quarantine** -- a drop with ZERO recoverable records that was already non-ok at the base ref moves,
  byte for byte, to ``shipwright_events.quarantine/`` (never read). The CI checker re-derives the same facts.

Before folding, the whole log (legacy + archive + drops) is scanned for ids: the same id with DIFFERENT content
as an event being folded is a conflict and stops the fold (``allow_conflicts`` keeps both). Never folds blindly.

Callers hold nothing; every change runs under the events lock (the writers' own lock). The caller stages.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .atomic_write import durable_atomic_write
from .events_fold_io import (
    KEEP_NAME, Parsed, blob, content_hash, dump_line, event_hash, name_problem, parse_bytes, same_bytes, sort_key, tree_names,
)
from .events_layout import events_lock_path
from .events_log import ARCHIVE_DIR, DROPS_DIR, QUARANTINE_DIR, event_files
from .events_read import instant
from .file_lock import FileLock

FOLD_AGE_DAYS = 14
SYNC_CONFIG = "shipwright_sync_config.json"


@dataclass
class Selected:
    path: Path
    data: bytes
    parsed: Parsed


@dataclass
class FoldPlan:
    mode: str
    selected: list[Selected] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    benign_duplicates: int = 0

    @property
    def archive_name(self) -> str | None:
        if not self.selected:
            return None
        digest = hashlib.sha256()
        for item in sorted(self.selected, key=lambda s: s.path.name):
            digest.update(item.path.name.encode() + b"\0" + hashlib.sha256(item.data).digest())
        return f"fold-{digest.hexdigest()[:12]}.jsonl"

    def records(self) -> list[dict]:
        return sorted((r for s in self.selected for r in s.parsed.records), key=sort_key)


def _drop_paths(root: Path) -> list[Path]:
    folder = root / DROPS_DIR
    if not folder.is_dir() or folder.is_symlink():
        return []
    return sorted(p for p in folder.glob("*.jsonl") if p.is_file() and not p.is_symlink())


def find_conflicts(root: Path, selected: list[Selected]) -> tuple[list[str], int]:
    """(ids that carry different content than an event being folded, count of identical copies elsewhere)."""
    chosen = {s.path.resolve() for s in selected}
    folding: dict[str, set[str]] = {}
    for s in selected:
        for r in s.parsed.records:
            if isinstance(r.get("id"), str):
                folding.setdefault(r["id"], set()).add(content_hash(r))
    elsewhere: dict[str, set[str]] = {}
    copies = 0
    for path in event_files(root):
        if path.resolve() in chosen or not path.exists():
            continue
        for r in parse_bytes(path.read_bytes()).records:
            ident = r.get("id")
            if ident in folding:
                elsewhere.setdefault(ident, set()).add(content_hash(r))
                copies += content_hash(r) in folding[ident]
    conflicts = sorted(i for i, hs in elsewhere.items() if hs - folding[i])
    conflicts += sorted(i for i, hs in folding.items() if len(hs) > 1 and i not in conflicts)
    return conflicts, copies


def plan_fold(root: Path | str, *, mode: str = "fold", base_ref: str = "HEAD", now: datetime | None = None,
              max_age_days: int = FOLD_AGE_DAYS, include_corrupt: bool = False) -> FoldPlan:
    """Decide what a fold would move (``mode``: ``fold`` | ``emergency``); touches nothing."""
    root, plan = Path(root), FoldPlan(mode)
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=max_age_days)
    merged = tree_names(root, base_ref, DROPS_DIR) if mode == "fold" else set()
    for path in _drop_paths(root):
        def skip(reason: str, _p: Path = path) -> None:
            plan.skipped.append({"file": _p.name, "reason": reason})

        if name_problem(DROPS_DIR, path.name):
            skip("name is not a legal drop name")
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            skip(f"unreadable: {exc.__class__.__name__}")
            continue
        parsed = parse_bytes(data)
        if parsed.status == "empty" or (parsed.status == "corrupt" and not (include_corrupt and parsed.records)):
            skip(f"{parsed.status} -- " + ("recoverable records present: pass include_corrupt to fold them"
                                           if parsed.records else "no recoverable record: quarantine candidate"))
            continue
        if mode == "fold":
            if merged is None:
                skip("base ref unreadable -- cannot tell whether the drop is merged")
            elif path.name not in merged or not same_bytes(blob(root, base_ref, f"{DROPS_DIR}/{path.name}") or b"missing", data):
                skip("not on the base ref unchanged (not merged yet, or modified)")
            elif any(instant(r.get("ts")) > cutoff or not isinstance(r.get("ts"), str) for r in parsed.records):
                skip(f"has events newer than {max_age_days} days (or without a ts)")
            else:
                plan.selected.append(Selected(path, data, parsed))
        else:
            plan.selected.append(Selected(path, data, parsed))
    plan.conflicts, plan.benign_duplicates = find_conflicts(root, plan.selected)
    return plan


def ensure_keep(root: Path) -> None:
    """Create the empty ``.keep`` in the drops folder (see ``events_fold_io.KEEP_NAME``); idempotent."""
    keep = root / DROPS_DIR / KEEP_NAME
    if not keep.exists():
        keep.parent.mkdir(exist_ok=True)
        durable_atomic_write(keep, b"")


def set_layout(root: Path | str, value: str) -> None:
    """Write ``events_layout`` into the sync config (other keys untouched; created when absent)."""
    path = Path(root) / SYNC_CONFIG
    cfg = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    cfg["events_layout"] = value
    durable_atomic_write(path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")


def apply_fold(root: Path | str, plan: FoldPlan, *, allow_conflicts: bool = False) -> dict:
    """Write the archive, verify it holds every folded event, then delete the folded drops."""
    root = Path(root)
    if plan.conflicts and not allow_conflicts:
        return {"status": "conflict", "conflicting_ids": plan.conflicts, "skipped": plan.skipped}
    name = plan.archive_name
    if name is None:
        return {"status": "nothing_to_fold", "skipped": plan.skipped}
    with FileLock(events_lock_path(root)):
        for item in plan.selected:  # a writer may have touched a file since the plan
            if item.path.read_bytes() != item.data:
                return {"status": "changed_since_plan", "file": item.path.name}
        archive = root / ARCHIVE_DIR / name
        archive.parent.mkdir(exist_ok=True)
        durable_atomic_write(archive, "".join(dump_line(r) + "\n" for r in plan.records()))
        stored = {event_hash(r) for r in parse_bytes(archive.read_bytes()).records}
        missing = [h for s in plan.selected for r in s.parsed.records if (h := event_hash(r)) not in stored]
        if missing:  # never delete a source the archive does not hold
            return {"status": "archive_incomplete", "missing": len(missing)}
        for item in plan.selected:
            try:
                item.path.unlink()
            except FileNotFoundError:
                pass  # a concurrent fold got there first
        ensure_keep(root)
        if plan.mode == "emergency":
            set_layout(root, "legacy")
    return {"status": "folded", "mode": plan.mode, "archive": f"{ARCHIVE_DIR}/{name}",
            "folded_files": [s.path.name for s in plan.selected], "events": len(plan.records()),
            "benign_duplicates": plan.benign_duplicates, "skipped": plan.skipped}


def plan_quarantine(root: Path | str, *, base_ref: str = "HEAD") -> list[Selected]:
    """Drops with zero recoverable records that were non-ok at ``base_ref`` and are unchanged since."""
    root, out = Path(root), []
    for path in _drop_paths(root):
        base = blob(root, base_ref, f"{DROPS_DIR}/{path.name}")
        if base is None or name_problem(DROPS_DIR, path.name):
            continue
        parsed = parse_bytes(base)
        if parsed.status != "ok" and not parsed.records and same_bytes(path.read_bytes(), base):
            out.append(Selected(path, base, parsed))
    return out


def apply_quarantine(root: Path | str, items: list[Selected]) -> dict:
    root = Path(root)
    if not items:
        return {"status": "nothing_to_quarantine"}
    with FileLock(events_lock_path(root)):
        (root / QUARANTINE_DIR).mkdir(exist_ok=True)
        for item in items:
            target = root / QUARANTINE_DIR / item.path.name
            durable_atomic_write(target, item.data)
            if target.read_bytes() != item.data:
                return {"status": "copy_mismatch", "file": item.path.name}
            os.unlink(item.path)
    return {"status": "quarantined", "files": [i.path.name for i in items]}

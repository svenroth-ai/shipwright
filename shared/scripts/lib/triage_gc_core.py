"""The triage-backlog GC engine: decide what is machine churn, and compact it.

Extracted from ``tools/triage_gc.py`` (which sat at exactly 300 of 300 LOC, so the
warning and ``--commit`` that audit 2026-07-28 finding 16 asks for had nowhere to
go). That module is now a thin CLI and re-exports every name below, so
``import triage_gc`` / ``from tools import triage_gc`` are unchanged.

Policy vocabulary (``MACHINE_DISMISSERS``/``MACHINE_REASONS``/``is_machine_churn``)
lives in :mod:`lib.triage_gc_policy`, and tracked-only resolution
(``_resolve_tracked_only``) lives in :mod:`lib.triage_gc_resolve` — both
re-exported here — split out when this module crossed the 300-LOC guideline
(iterate-2026-08-08-triage-amend-event's amend overlay, then again for that
resolution's Stage-3 doubt-review fix). See those modules for their own
rationale.

The store is an append-only event log (``append`` + ``status`` + ``amend``, all
carrying ``id``); "dropping" an item rewrites the log without its lines — a
destructive compaction, which is why the CLI defaults to a dry run. A dropped id's
``amend`` lines are compacted away with its ``append``/``status`` — see the `kept`
filter in :func:`apply_gc_reporting` and the matching orphan check in
:func:`_validate_after` (iterate-2026-08-08-triage-amend-event, AC11).
"""

from __future__ import annotations

import contextlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Make the triage store importable whether invoked from the repo root or
# elsewhere (mirrors lib/reconcile_triage.py's shim).
_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402
from lib.atomic_write import durable_atomic_write, replace_retrying  # noqa: E402
from lib.jsonl_records import split_records  # noqa: E402
from lib.triage_gc_policy import (  # noqa: E402,F401  (re-export surface)
    MACHINE_DISMISSERS,
    MACHINE_REASONS,
    is_machine_churn,
)
from lib.triage_gc_resolve import resolve_tracked_only as _resolve_tracked_only  # noqa: E402,F401  (re-export surface)


def plan_gc(project_root: Path | str) -> dict:
    """Compute the GC plan without writing anything.

    Operates on the TRACKED store only (D1) — the outbox is GC'd by the D2
    sweep, never by this CLI.

    Returns ``{"drop_ids": set, "dropped": [item...], "kept_count": int,
    "total": int}``.
    """
    items = _resolve_tracked_only(project_root)
    dropped = [i for i in items if is_machine_churn(i)]
    drop_ids = {i["id"] for i in dropped}
    return {
        "drop_ids": drop_ids,
        "dropped": dropped,
        "kept_count": len(items) - len(dropped),
        "total": len(items),
    }


def _union_droppable_ids(project_root: Path | str) -> set[str]:
    """Ids that are machine-churn by UNION residence (tracked ∪ outbox,
    last-status-wins — :func:`triage.read_all_items`).

    The under-lock recompute in :func:`apply_gc` uses THIS, not the tracked-only
    :func:`plan_gc`, so a concurrent re-open routed to the gitignored OUTBOX
    (idle-main-with-origin) flips the item out of the set and survives. The report
    stays tracked-only (D1); the intersection keeps it an upper bound.
    """
    return {
        i["id"] for i in triage.read_all_items(project_root)
        if is_machine_churn(i)
    }


def _validate_after(project_root: Path | str, drop_ids: set[str]) -> None:
    """Fail loudly if the rewrite produced an inconsistent TRACKED log.

    D1: GC compacts the tracked store only, so validation reads the tracked path
    directly (NOT the union ``read_all_items`` / ``_iter_raw_lines``) — otherwise an
    OUTBOX-resident status whose append GC just dropped would false-trip the
    orphan-status check, and an outbox item would count as a survivor.
    """
    raw = triage._iter_raw_lines_at(triage._triage_path(project_root))
    if not raw or raw[0].get("schema") != "triage":
        raise RuntimeError("post-GC validation: header missing or malformed")
    append_ids = {r.get("id") for r in raw if r.get("event") == "append"}
    for r in raw:
        # `amend` alongside `status` (iterate-2026-08-08-triage-amend-event, AC11) —
        # MUST ship with the `kept` filter below also dropping amend lines for a
        # churned id, or this raises on every future run over a survivor it can
        # never un-drop (a permanent GC block, the exact class this fix prevents).
        if r.get("event") in ("status", "amend") and r.get("id") not in append_ids:
            raise RuntimeError(
                f"post-GC validation: orphan {r.get('event')} event for id={r.get('id')}"
            )
        if r.get("id") in drop_ids:
            raise RuntimeError(
                f"post-GC validation: dropped id={r.get('id')} still present"
            )
    survivors = {i["id"] for i in _resolve_tracked_only(project_root)}
    if survivors & drop_ids:
        raise RuntimeError("post-GC validation: a dropped item resolved as surviving")


def _records_from_text(text: str) -> list[dict]:
    """Parse already-read log text into records, mirroring
    :func:`lib.jsonl_records.read_jsonl_records` but over bytes the caller
    ALREADY holds.

    Why not call the path reader again: :func:`apply_gc_reporting` needs the backup and
    the compaction input to be the same version. It used to read twice — ``read_text``
    for the backup and the JSON scan, ``_iter_raw_lines_at`` for the rewrite input — so
    an append landing between them left the ``.bak`` preserving a file that was never
    the one compacted (external plan review, round 2). Same SSoT parser, one read.
    """
    records: list[dict] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        parsed, remainder = split_records(stripped)
        if remainder:
            # Unreachable while the caller's malformed-JSON scan runs first; if the
            # two ever disagree, refuse rather than compact an unreadable line away.
            raise RuntimeError(
                f"triage_gc: refusing to rewrite — unrecoverable fragment at line {line_no}"
            )
        records.extend(parsed)
    return records


@dataclass(frozen=True)
class GcApply:
    """What :func:`apply_gc_reporting` actually did.

    ``written_text`` is the exact content published to the tracked log. A caller
    that wants to COMMIT the compaction needs it: it must prove the file it is
    about to commit is still the one GC produced, and re-reading the file cannot
    prove that (external plan review, round 2).
    """

    backup_path: Path
    written_text: str
    dropped: int


def apply_gc_reporting(
    project_root: Path | str, drop_ids: set[str], backup: bool = True
) -> GcApply:
    """Rewrite the log dropping the machine-churn lines. Holds the store's file lock.

    F19 (TOCTOU): ``drop_ids`` is the caller's out-of-lock plan, so the decision is
    **recomputed under the lock** over union residence and intersected with it (see
    :func:`_union_droppable_ids`). The intersection keeps the operator-facing report an
    upper bound: apply never drops MORE than announced. Refuses outright if any
    non-blank line is malformed JSON — the tolerant reader would otherwise compact a
    corrupt line away.

    **Durability (audit 2026-07-28, finding 9).** Both writes go through
    :func:`durable_atomic_write` — bounded retry past a Windows sharing violation plus
    a parent-dir fsync, neither of which the hand-rolled tmp+fsync+replace had. The
    ``.bak`` used ``write_text``: not durable, and not newline-neutral (measured, an LF
    log's backup came back CRLF), so it is now written from the original BYTES.
    """
    path = triage._triage_path(project_root)
    with triage._FileLock(triage._lock_path(project_root)):
        original_bytes = path.read_bytes() if path.exists() else b""
        # STRICT decode, as before: this rewrites a tracked artifact wholesale, so a
        # byte we cannot read is a reason to refuse, not to round-trip blindly.
        original_text = original_bytes.decode("utf-8")
        for n, line in enumerate(original_text.splitlines(), start=1):
            if line.strip():
                try:
                    json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"triage_gc: refusing to rewrite — malformed JSON at line "
                        f"{n} ({exc.msg}); fix or remove it first"
                    )
        # Recompute UNDER the lock over union residence (see docstring): a
        # concurrent re-open in the tracked log OR the gitignored outbox flips
        # the item out of the set and survives. Closes the a1-6/F19 outbox-route
        # gap. Intersect with the caller's plan; rewrite only the tracked file.
        fresh_drop_ids = _union_droppable_ids(project_root)
        effective_drop_ids = fresh_drop_ids & set(drop_ids)
        # Tracked store only, and from the bytes read above — never a second read.
        kept = [
            r for r in _records_from_text(original_text)
            if r.get("event") not in ("append", "status", "amend") or r.get("id") not in effective_drop_ids
        ]
        new_text = "\n".join(
            json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in kept
        ) + "\n"
        # Backup FSYNCED here, before the compare, then PUBLISHED by a rename after it.
        # Writing it after the compare bought "a refusal leaves no .bak" by moving a
        # whole-file fsync inside the compare→publish window (doubt review).
        backup_path = path.with_suffix(path.suffix + ".bak")
        backup_tmp = path.with_suffix(path.suffix + ".bak.tmp")
        writing_backup = bool(backup and original_bytes)
        if writing_backup:
            durable_atomic_write(backup_tmp, original_bytes)
        # Re-read before publishing. The canonical lock is held across this whole
        # section, but the WebUI writer uses `proper-lockfile` and does not take it
        # (triage_repair.py:30-36), so it can still have appended since the read, and
        # overwriting that append is the data loss this module exists to avoid. This
        # narrows the window; it does not close it — `durable_atomic_write` still fsyncs
        # the NEW text before its rename (residual named, as in reconcile_rollback).
        if (path.read_bytes() if path.exists() else b"") != original_bytes:
            if writing_backup:
                # No .bak for a compaction that never happened — and no CLOBBERING of a
                # good one from an earlier run, which is why .bak is replaced only after
                # the compare passes.
                with contextlib.suppress(OSError):
                    backup_tmp.unlink()
            raise RuntimeError(
                "triage_gc: refusing to rewrite — the tracked log changed under us "
                "between the read and the write (a writer that does not take the "
                "canonical lock). Nothing was published; re-run."
            )
        if writing_backup:
            replace_retrying(backup_tmp, backup_path)
        durable_atomic_write(path, new_text)
        # Validate against the SET WE ACTUALLY DROPPED (F19): an id present in the
        # caller's stale plan but re-opened (so excluded from effective_drop_ids)
        # is legitimately still present — validating against the stale plan would
        # false-fail. Run under the lock so no concurrent writer interleaves.
        _validate_after(project_root, effective_drop_ids)
    return GcApply(backup_path=backup_path if backup else path,
                   written_text=new_text, dropped=len(effective_drop_ids))


def apply_gc(project_root: Path | str, drop_ids: set[str], backup: bool = True) -> Path:
    """:func:`apply_gc_reporting` with its historical return: the backup path (or the
    live path when ``backup`` is False)."""
    return apply_gc_reporting(project_root, drop_ids, backup).backup_path

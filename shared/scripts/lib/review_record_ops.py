"""Locked read-modify-write operations on the review record.

Split from :mod:`lib.review_record` (shape + plain IO) to stay under the
300-line file limit and because these three are the only operations that take
the run's lock. ``review_record`` re-exports them, so every existing import
path keeps resolving.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .file_lock import file_lock
from .review_record_core import (
    TERMINAL_STATUSES,
    ReviewRecordError,
    lock_path,
    new_record,
    read_record,
    record_dir,
    upsert_review,
    write_record,
)

__all__ = ["close_pending", "init_record", "repair_companion", "upsert_and_write"]


def init_record(
    project_root: Path | str, run_id: str, *, lock_timeout_seconds: float = 10.0
) -> tuple[dict[str, Any], bool]:
    """Create-if-absent. Returns ``(record, created)``.

    Never replaces an existing record — a populated one is returned untouched
    and a corrupt one raises. An ``init`` that could clobber would make every
    re-run of a resumed iterate a chance to erase its own review history.
    """
    record_dir(project_root, run_id).mkdir(parents=True, exist_ok=True)
    with file_lock(lock_path(project_root, run_id), timeout_seconds=lock_timeout_seconds):
        existing = read_record(project_root, run_id)
        if existing is not None:
            return existing, False
        record = new_record(run_id)
        write_record(project_root, run_id, record)
        return record, True


def upsert_and_write(
    project_root: Path | str,
    run_id: str,
    entry: dict[str, Any],
    *,
    force: bool = False,
    lock_timeout_seconds: float = 10.0,
    after_write: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Read-modify-write one entry under the run's lock.

    Read, immutability check and write all happen inside ONE lock so two passes
    recording concurrently cannot lose each other's entry, and so a rejected
    upsert never leaves a partially-applied record behind.

    ``after_write`` runs while the lock is STILL HELD, for a companion artifact
    that must not observe a record another writer has since moved on from — the
    legacy ``external_*review_state.json`` marker is written through it. The
    record is written first and remains authoritative: if ``after_write``
    raises, the record stands and the companion is repairable.
    """
    record_dir(project_root, run_id).mkdir(parents=True, exist_ok=True)
    with file_lock(lock_path(project_root, run_id), timeout_seconds=lock_timeout_seconds):
        record = read_record(project_root, run_id) or new_record(run_id)
        record = upsert_review(record, entry, force=force)
        write_record(project_root, run_id, record)
        if after_write is not None:
            after_write(record)
        return record


def close_pending(
    project_root: Path | str,
    run_id: str,
    entries: list[dict[str, Any]],
    *,
    lock_timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Close several types in ONE write under ONE lock — all or nothing.

    Closing them one acquisition at a time meant a mid-loop failure (lock
    timeout, ENOSPC, a concurrent recorder) left some types permanently closed
    and the rest open. Every close is terminal and therefore irreversible
    without ``--force``, so a half-applied batch is an irreversible half-state
    produced by the very command whose job is to unblock a stuck run.
    """
    record_dir(project_root, run_id).mkdir(parents=True, exist_ok=True)
    with file_lock(lock_path(project_root, run_id), timeout_seconds=lock_timeout_seconds):
        record = read_record(project_root, run_id) or new_record(run_id)
        for entry in entries:
            record = upsert_review(record, entry)
        write_record(project_root, run_id, record)
        return record


def repair_companion(
    project_root: Path | str,
    run_id: str,
    review_type: str,
    action: Callable[[dict[str, Any]], None],
    *,
    lock_timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Re-run ``action`` against the ALREADY-RECORDED entry, without rewriting it.

    The repair path for a companion artifact whose write failed after the record
    landed. Re-running the original command cannot serve this purpose — it hits
    the immutability guard and exits before reaching the companion — and
    ``--force`` would rewrite the authoritative record just to fix a marker.
    """
    with file_lock(lock_path(project_root, run_id), timeout_seconds=lock_timeout_seconds):
        record = read_record(project_root, run_id)
        if record is None:
            raise ReviewRecordError(f"no review record for {run_id} to repair from")
        entry = record.get("reviews", {}).get(review_type) or {}
        if entry.get("status") not in TERMINAL_STATUSES:
            raise ReviewRecordError(
                f"{review_type} is not recorded yet — nothing to repair from"
            )
        action(record)
        return record

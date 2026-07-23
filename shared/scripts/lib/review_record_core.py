"""Shape, validation wiring and plain IO for the per-run review record.

One file per run, git-tracked, never evicted::

    .shipwright/planning/iterate/<run_id>/reviews.json

**Why this exists.** The internal reviewers (``code-reviewer``,
``doubt-reviewer``) already return structured JSON and the Self-Review already
produces a per-item verdict, but the iterate lifecycle preserved none of it —
the result survived only as prose in an ADR. The Mission view's Review artifact
therefore had nothing to read for three of five review types, and the two it
could read were written to ONE shared, run-agnostic file that every run
overwrote. This module is the missing durable half.

**Keyed by type, not a list.** ``reviews`` is a dict over the five review types
so "every type is represented" is structural rather than a convention a writer
can forget, and so a type cannot appear twice. A type nobody has recorded yet
reads ``pending`` — explicitly present and explicitly unanswered, which is the
whole point of the artifact: an empty Review row must mean "genuinely not run",
never "somebody forgot to write it down".

**Immutability.** A review that reached a terminal status is not rewritable
(:class:`ImmutableReviewError`) without an explicit ``force``. A record of what
a review found is worthless if a later pass can quietly restate it.

Disk is snake_case per this repo's convention; the webui consumer already maps
snake_case onto its camelCase ``ReviewRow``, so the pinned
``{reviewType, status, findingsCount, findings[]}`` descriptor is unchanged.
The vocabulary and the schema check live in :mod:`lib.review_record_schema`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .atomic_write import durable_atomic_write
from .review_record_schema import (
    ALL_STATUSES,
    NEEDS_DISPOSITION,
    REVIEW_TYPES,
    SCHEMA_VERSION,
    STATUS_PENDING,
    TERMINAL_STATUSES,
    disposition_ok,
    is_safe_run_id,
    validate_record,
)

__all__ = [
    "ImmutableReviewError",
    "ReviewRecordError",
    "lock_path",
    "make_entry",
    "new_record",
    "pending_types",
    "read_record",
    "record_dir",
    "record_path",
    "upsert_review",
    "write_record",
]


class ReviewRecordError(RuntimeError):
    """Raised on an invalid record, entry, or unreadable file."""


class ImmutableReviewError(ReviewRecordError):
    """Raised when an upsert would overwrite a terminal review status."""


# --- paths ------------------------------------------------------------------


def record_dir(project_root: Path | str, run_id: str) -> Path:
    """The run-scoped planning dir — also where the run-scoped copies of the
    ``external_*review_state.json`` markers land, which is exactly where the
    webui consumer already looks.

    ``run_id`` is validated because it becomes a path component: an absolute
    value would silently REPLACE ``project_root`` and a ``..`` value would climb
    out of the planning dir.
    """
    if not is_safe_run_id(run_id):
        raise ReviewRecordError(
            f"unsafe run_id {run_id!r} — must be a single path component "
            "(letters, digits, dot, dash, underscore)"
        )
    return Path(project_root) / ".shipwright" / "planning" / "iterate" / run_id


def record_path(project_root: Path | str, run_id: str) -> Path:
    return record_dir(project_root, run_id) / "reviews.json"


def lock_path(project_root: Path | str, run_id: str) -> Path:
    return record_dir(project_root, run_id) / "reviews.json.lock"


# --- construction -----------------------------------------------------------


def make_entry(
    review_type: str,
    status: str,
    *,
    findings: list[dict[str, Any]] | None = None,
    provider: str | None = None,
    disposition: str | None = None,
    completed_at: str | None = None,
    recorded_by: str | None = None,
    parse_status: str | None = None,
    raw_excerpt: str | None = None,
) -> dict[str, Any]:
    """Build one review entry.

    ``findings_count`` is DERIVED from ``findings``, never supplied — a count
    that can disagree with the list it counts is a count nobody can trust.
    """
    if review_type not in REVIEW_TYPES:
        raise ReviewRecordError(f"unknown review_type: {review_type!r}")
    if status not in ALL_STATUSES:
        raise ReviewRecordError(f"unknown status: {status!r}")
    items = list(findings or [])
    if status in NEEDS_DISPOSITION and not disposition_ok(disposition):
        raise ReviewRecordError(
            f"status {status!r} requires a disposition naming the rule that "
            f"applies (more than one word) — got {disposition!r}"
        )
    return {
        "review_type": review_type,
        "status": status,
        "findings_count": len(items),
        "findings": items,
        "provider": provider,
        "completed_at": completed_at,
        "disposition": disposition,
        "recorded_by": recorded_by,
        "parse_status": parse_status,
        "raw_excerpt": raw_excerpt,
    }


def new_record(run_id: str) -> dict[str, Any]:
    """A record with all five types materialized as ``pending``."""
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "reviews": {t: make_entry(t, STATUS_PENDING) for t in REVIEW_TYPES},
    }


def upsert_review(
    record: dict[str, Any], entry: dict[str, Any], *, force: bool = False
) -> dict[str, Any]:
    """Place ``entry`` into ``record``, refusing to overwrite a terminal status."""
    review_type = entry.get("review_type")
    if review_type not in REVIEW_TYPES:
        raise ReviewRecordError(f"unknown review_type: {review_type!r}")
    existing = record.get("reviews", {}).get(review_type) or {}
    if not force and existing.get("status") in TERMINAL_STATUSES:
        raise ImmutableReviewError(
            f"{review_type} is already recorded as {existing['status']!r} and a "
            "completed review is immutable — pass --force only to correct a "
            "genuinely wrong record"
        )
    updated = dict(record)
    updated["reviews"] = dict(record.get("reviews", {}))
    updated["reviews"][review_type] = entry
    return updated


def pending_types(record: dict[str, Any]) -> list[str]:
    """Types that have not reached a terminal status — in contract order."""
    reviews = record.get("reviews", {}) or {}
    return [
        t for t in REVIEW_TYPES
        if (reviews.get(t) or {}).get("status", STATUS_PENDING) == STATUS_PENDING
    ]


# --- IO ---------------------------------------------------------------------


def _serialize(record: dict[str, Any]) -> str:
    return json.dumps(record, indent=2, ensure_ascii=False) + "\n"


def read_record(
    project_root: Path | str, run_id: str, *, validate: bool = True
) -> dict[str, Any] | None:
    """Read the record. ``None`` when absent; raises when present-but-broken —
    an unreadable record is a data-integrity fault and must never be reported
    as an absence."""
    path = record_path(project_root, run_id)
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise ReviewRecordError(f"{path} is unreadable: {exc}") from exc
    if validate:
        ok, err = validate_record(record, expected_run_id=run_id)
        if not ok:
            raise ReviewRecordError(f"{path} is schema-invalid: {err}")
    return record


def write_record(project_root: Path | str, run_id: str, record: dict[str, Any]) -> Path:
    """Validate then durably write. Validation runs BEFORE the write so a
    malformed record never reaches disk."""
    ok, err = validate_record(record, expected_run_id=run_id)
    if not ok:
        raise ReviewRecordError(f"refusing to write an invalid record: {err}")
    path = record_path(project_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    durable_atomic_write(path, _serialize(record))
    return path

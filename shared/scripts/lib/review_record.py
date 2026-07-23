"""The per-run review record — what every review pass of an iterate found.

One file per run, git-tracked, never evicted::

    .shipwright/planning/iterate/<run_id>/reviews.json

**Why this exists.** The internal reviewers (``code-reviewer``,
``doubt-reviewer``) already return structured JSON and the Self-Review already
produces a per-item verdict, but the iterate lifecycle preserved none of it —
the result survived only as prose in an ADR. The Mission view's Review artifact
therefore had nothing to read for three of five review types, and the two it
could read were written to ONE shared, run-agnostic file that every run
overwrote. This is the missing durable half.

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

This module is the FACADE — one import site for the whole record API. The parts
live in three modules only because each would otherwise breach the 300-line
file limit:

* :mod:`lib.review_record_schema` — the vocabulary and the schema check
* :mod:`lib.review_record_core` — shape, construction, plain IO
* :mod:`lib.review_record_ops` — the three operations that take the run's lock
"""

from __future__ import annotations

from .review_record_core import (
    ImmutableReviewError,
    ReviewRecordError,
    lock_path,
    make_entry,
    new_record,
    pending_types,
    read_record,
    record_dir,
    record_path,
    upsert_review,
    write_record,
)
from .review_record_ops import (
    close_pending,
    init_record,
    repair_companion,
    upsert_and_write,
)
from .review_record_schema import (
    ALL_STATUSES,
    REVIEW_TYPES,
    SCHEMA_VERSION,
    STATUS_COMPLETED,
    STATUS_NOT_APPLICABLE,
    STATUS_NOT_RUN,
    STATUS_PENDING,
    TERMINAL_STATUSES,
    is_safe_run_id,
    validate_record,
)

__all__ = [
    "ALL_STATUSES",
    "REVIEW_TYPES",
    "SCHEMA_VERSION",
    "STATUS_COMPLETED",
    "STATUS_NOT_APPLICABLE",
    "STATUS_NOT_RUN",
    "STATUS_PENDING",
    "TERMINAL_STATUSES",
    "ImmutableReviewError",
    "ReviewRecordError",
    "close_pending",
    "init_record",
    "is_safe_run_id",
    "lock_path",
    "make_entry",
    "new_record",
    "pending_types",
    "read_record",
    "record_dir",
    "record_path",
    "repair_companion",
    "upsert_and_write",
    "upsert_review",
    "validate_record",
    "write_record",
]

"""Vocabulary and validation for the per-run review record.

Split out of :mod:`lib.review_record` to stay under the 300-line file limit, and
because the two halves are genuinely separable: this module owns *what a
well-formed record is*, that one owns *how one is built and stored*. The
dependency runs one way — record imports schema — so the vocabulary has a single
home and there is no cycle.

Validation is deliberately strict and total. The F11 gate treats any violation
as corrupt, so a record that passes here is one every consumer may trust without
re-checking; anything looser would let a malformed record (missing types, a
count that disagrees with its own list, a terminal status with no justification)
present itself as a clean review history.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "ALL_STATUSES",
    "NEEDS_DISPOSITION",
    "REVIEW_TYPES",
    "SCHEMA_VERSION",
    "SEVERITIES",
    "STATUS_COMPLETED",
    "STATUS_NOT_APPLICABLE",
    "STATUS_NOT_RUN",
    "STATUS_PENDING",
    "TERMINAL_STATUSES",
    "disposition_ok",
    "is_safe_run_id",
    "validate_entry",
    "validate_record",
]

SCHEMA_VERSION = 1

#: Contract order — plan · code · doubt · external_code are the four types the
#: webui Mission contract pins; ``self`` is the fifth, added because at trivial
#: and small complexity the Self-Review is the ONLY review that runs, and a
#: Review artifact showing four empty rows for the commonest case would be
#: actively misleading.
REVIEW_TYPES = ("self", "plan", "code", "doubt", "external_code")

STATUS_PENDING = "pending"
STATUS_COMPLETED = "completed"
STATUS_NOT_RUN = "not_run"
STATUS_NOT_APPLICABLE = "not_applicable"

#: A terminal status is an answer; ``pending`` is the absence of one.
TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_NOT_RUN, STATUS_NOT_APPLICABLE})
ALL_STATUSES = TERMINAL_STATUSES | {STATUS_PENDING}

#: Statuses that must justify themselves. ``completed`` needs none — the
#: findings are the record. "Did not run" does, or the gate degrades into a
#: box-ticking exercise (external plan review O7).
NEEDS_DISPOSITION = frozenset({STATUS_NOT_RUN, STATUS_NOT_APPLICABLE})

SEVERITIES = frozenset({"high", "medium", "low"})

#: A disposition must name a RULE, not wave at one. Enforced structurally
#: because "skipped" / "n/a" is exactly how an unreviewed change gets laundered
#: into a passing gate.
_MIN_DISPOSITION_CHARS = 12

_OPTIONAL_STRINGS = (
    "provider", "completed_at", "disposition", "recorded_by",
    "parse_status", "raw_excerpt",
)


#: A run id becomes a DIRECTORY NAME under .shipwright/planning/iterate/, so it
#: must be exactly one safe path component. Without this, ``record_dir`` would
#: happily join `../../..` (traversal) or an absolute path (which silently
#: REPLACES the project root on both POSIX and Windows) — found in self-review.
#: Mirrors the webui consumer's own `isSafeRunId` guard on the same identifier.
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MAX_RUN_ID_CHARS = 128


def is_safe_run_id(run_id: Any) -> bool:
    """True when ``run_id`` is usable as a single filesystem path component."""
    if not isinstance(run_id, str):
        return False
    if not (0 < len(run_id) <= _MAX_RUN_ID_CHARS):
        return False
    if run_id in (".", ".."):
        return False
    return bool(_SAFE_RUN_ID_RE.match(run_id))


def disposition_ok(value: Any) -> bool:
    """True when ``value`` names a rule rather than waving at one."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    return len(text) >= _MIN_DISPOSITION_CHARS and " " in text


def _validate_finding(item: Any, where: str) -> str | None:
    if not isinstance(item, dict):
        return f"{where}: finding is not an object"
    text = item.get("finding")
    if not isinstance(text, str) or not text.strip():
        return f"{where}: finding text is empty"
    severity = item.get("severity")
    if severity is not None and severity not in SEVERITIES:
        return f"{where}: severity {severity!r} is not one of {sorted(SEVERITIES)} or null"
    line = item.get("line")
    if line is not None and (isinstance(line, bool) or not isinstance(line, int)):
        return f"{where}: line must be an integer or null"
    for key in ("file", "suggestion", "category", "source"):
        value = item.get(key)
        if value is not None and not isinstance(value, str):
            return f"{where}: {key} must be a string or null"
    return None


def validate_entry(review_type: str, entry: Any) -> str | None:
    """Return an error string, or ``None`` when ``entry`` is well-formed."""
    where = f"reviews.{review_type}"
    if not isinstance(entry, dict):
        return f"{where} is not an object"
    if entry.get("review_type") != review_type:
        return (
            f"{where}.review_type is {entry.get('review_type')!r} but the key "
            f"says {review_type!r}"
        )
    status = entry.get("status")
    if status not in ALL_STATUSES:
        return f"{where}.status {status!r} is not one of {sorted(ALL_STATUSES)}"
    findings = entry.get("findings")
    if not isinstance(findings, list):
        return f"{where}.findings is not a list"
    if entry.get("findings_count") != len(findings):
        return (
            f"{where}.findings_count is {entry.get('findings_count')!r} but "
            f"findings has {len(findings)} item(s)"
        )
    for index, item in enumerate(findings):
        err = _validate_finding(item, f"{where}.findings[{index}]")
        if err:
            return err
    if status in NEEDS_DISPOSITION and not disposition_ok(entry.get("disposition")):
        return (
            f"{where}.status is {status!r} but its disposition does not name a "
            "rule (needs more than one word)"
        )
    for key in _OPTIONAL_STRINGS:
        value = entry.get(key)
        if value is not None and not isinstance(value, str):
            return f"{where}.{key} must be a string or null"
    return None


def validate_record(
    record: Any, *, expected_run_id: str | None = None
) -> tuple[bool, str | None]:
    """Full schema check — the authoritative definition of a well-formed record."""
    if not isinstance(record, dict):
        return False, "record is not an object"
    version = record.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        return False, f"schema_version {version!r} is not a positive integer"
    if version > SCHEMA_VERSION:
        return False, (
            f"schema_version {version} is newer than this tool understands "
            f"({SCHEMA_VERSION}) — upgrade rather than silently misreading it"
        )
    run_id = record.get("run_id")
    if not is_safe_run_id(run_id):
        return False, f"run_id {run_id!r} is not a safe single path component"
    if expected_run_id is not None and run_id != expected_run_id:
        return False, (
            f"run_id is {run_id!r} but this record was read for "
            f"{expected_run_id!r} — never trust the file's own idea of which "
            "run it belongs to"
        )
    reviews = record.get("reviews")
    if not isinstance(reviews, dict):
        return False, "reviews is not an object"
    missing = [t for t in REVIEW_TYPES if t not in reviews]
    if missing:
        return False, f"reviews is missing: {', '.join(missing)}"
    unknown = [t for t in reviews if t not in REVIEW_TYPES]
    if unknown:
        return False, f"reviews has unknown type(s): {', '.join(sorted(unknown))}"
    for review_type in REVIEW_TYPES:
        err = validate_entry(review_type, reviews[review_type])
        if err:
            return False, err
    return True, None

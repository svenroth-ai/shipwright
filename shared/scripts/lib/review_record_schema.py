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

try:
    from .review_verdict import (
        HISTORICAL_REVIEWER_PAIRS,
        REVIEWERS,
        UNAVAILABLE,
        UNKNOWN,
        VERDICTS,
    )
except ImportError:
    from review_verdict import (  # type: ignore[no-redef]
        HISTORICAL_REVIEWER_PAIRS,
        REVIEWERS,
        UNAVAILABLE,
        UNKNOWN,
        VERDICTS,
    )

__all__ = [
    "ALL_STATUSES",
    "LEGACY_GATE_TYPES",
    "NEEDS_DISPOSITION",
    "RECORDABLE_TYPES",
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

#: Deliberately NOT bumped when ``gates`` was added, and NOT bumped when ``spec``
#: was promoted out of it. The reason changed shape but not direction.
#:
#: It used to be that the ONE external consumer compared this number with a
#: strict ``!==``, so a bump made the only reader stop understanding a file it
#: understood fine. That reader now treats the number as a FLOOR (``>=``), which
#: removes the old harm and adds no benefit: a bump would buy the consumer
#: nothing, while ``validate_record`` below still refuses a version NEWER than
#: it knows — so every plugin cache not yet updated becomes a casualty — and the
#: consumer appends a user-visible "written by a newer Shipwright, so a pass may
#: be missing" caveat to a record where nothing is missing.
#:
#: Bump when a reader must be STOPPED from misreading a reshaped entry. Adding a
#: key to :data:`REVIEW_TYPES` is not that: it is additive, and the consumer
#: renders what it does not recognise.
SCHEMA_VERSION = 1

#: Contract order — plan · code · doubt · external_code are the four types the
#: webui Mission contract pins; ``self`` is the fifth, added because at trivial
#: and small complexity the Self-Review is the ONLY review that runs, and a
#: Review artifact showing four empty rows for the commonest case would be
#: actively misleading. ``spec`` is Stage 1 of the cascade — the spec-compliance
#: HARD-GATE. Without a row of its own, a ``code`` row sourced ``code-reviewer``
#: is byte-identical whether Stage 1 passed first or was never spawned, which is
#: exactly the not-run-versus-not-recorded distinction this artifact exists to
#: abolish (``trg-64372769``).
#:
#: **The tuple may GROW but never shrink or rename.** ``spec`` used to be parked
#: in a sibling ``gates`` object because the consumer rejected a ``reviews`` key
#: outside its own five, and an invalid record does NOT degrade to the marker
#: fallback — it renders as a data-integrity fault (``review-state.ts``). The
#: consumer lifted that pin in ``shipwright-webui`` ``ce21323e`` (PR #339): a
#: key it does not recognise is now mapped and RENDERED as an extra row. It
#: still requires the five it knows to be present, so growth is additive only.
REVIEW_TYPES = ("self", "plan", "code", "doubt", "external_code", "spec")

#: Types a record may carry under the retired ``gates`` sibling — a READ
#: vocabulary, never a write destination.
#:
#: The seam existed for exactly one reason, stated in its own source: to hold
#: passes "the pinned ``reviews`` contract has no slot for". That pin is gone,
#: so a future gate stage goes straight into :data:`REVIEW_TYPES` and the seam
#: comes down rather than lingering as an empty tuple pretending to be an
#: extension point. What must survive is READING it: 12 git-tracked,
#: never-evicted records carry ``gates.spec`` and are immutable by design.
LEGACY_GATE_TYPES = ("spec",)

#: Everything ``record_review_pass.py`` will accept for ``--review-type``.
#: Identical to :data:`REVIEW_TYPES` now that the gate seam is retired; kept as
#: its own name because "what the CLI accepts" and "what a record must carry"
#: are different questions that were separate before and may separate again.
RECORDABLE_TYPES = REVIEW_TYPES

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
    "parse_status", "raw_excerpt", "contradiction_resolution", "model_tier",
)


#: A run id becomes a DIRECTORY NAME under .shipwright/planning/iterate/, so it
#: must be exactly one safe path component. Without this, ``record_dir`` would
#: happily join `../../..` (traversal) or an absolute path (which silently
#: REPLACES the project root on both POSIX and Windows) — found in self-review.
#: Mirrors the webui consumer's own `isSafeRunId` guard on the same identifier.
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MAX_RUN_ID_CHARS = 128
_REVIEW_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_MAX_REVIEW_TYPES = 32


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


def validate_entry(review_type: str, entry: Any, *, where: str | None = None) -> str | None:
    """Return an error string, or ``None`` when ``entry`` is well-formed."""
    where = where or f"reviews.{review_type}"
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
    if "verdicts" in entry:
        verdicts = entry["verdicts"]
        if not isinstance(verdicts, dict):
            return f"{where}.verdicts must be an object"
        supported = {frozenset(REVIEWERS), *map(frozenset, HISTORICAL_REVIEWER_PAIRS)}
        if frozenset(verdicts) not in supported:
            return f"{where}.verdicts has an unsupported reviewer set"
        allowed = {*VERDICTS, UNKNOWN, UNAVAILABLE}
        if any(value not in allowed for value in verdicts.values()):
            return f"{where}.verdicts contains an unknown verdict"
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
    # A type promoted out of the retired `gates` seam may legitimately be absent
    # from `reviews`: 12 records on disk keep it under `gates`, and 53 predate
    # the concept entirely. Requiring it here would make the F11 gate — which
    # fails CLOSED — tell the operator to "repair or delete" 65 immutable,
    # git-tracked review histories that are perfectly fine, which is precisely
    # the failure the consumer's own tolerant reader was built to stop.
    #
    # This buys back-compat for READING history and nothing for a live run:
    # `pending_types` counts an absent `spec` as unanswered in either section,
    # so a run cannot dodge the row by simply not writing it.
    missing = [
        t for t in REVIEW_TYPES
        if t not in reviews and t not in LEGACY_GATE_TYPES
    ]
    if missing:
        return False, f"reviews is missing: {', '.join(missing)}"
    if len(reviews) > _MAX_REVIEW_TYPES:
        return False, f"reviews has {len(reviews)} types; maximum is {_MAX_REVIEW_TYPES}"
    # Additive review types are a forward-compatible read surface. They do not
    # become required or writable merely by appearing, but their entries must
    # satisfy the same structural contract as every known row.
    for review_type, entry in reviews.items():
        if not isinstance(review_type, str) or not _REVIEW_KEY_RE.match(review_type):
            return False, f"reviews key {review_type!r} is not a safe reviewer identifier"
        err = validate_entry(review_type, entry)
        if err:
            return False, err
    return _validate_gates(record.get("gates"))


def _validate_gates(gates: Any) -> tuple[bool, str | None]:
    """The retired ``gates`` sibling — optional, but strict when present.

    Nothing writes this object any more; :data:`LEGACY_GATE_TYPES` names what
    old records put there. Absence is valid twice over now: records written
    before the seam existed have no such key, and records written after its
    retirement do not either. Invalidating either would make the F11 gate report
    an integrity fault on runs that are perfectly fine. Optional here is about
    READING history — a live run cannot use it to dodge the row, because
    ``pending_types`` counts an absent entry as unanswered in both sections.
    """
    if gates is None:
        return True, None
    if not isinstance(gates, dict):
        return False, "gates is not an object"
    # Unknown gate keys are tolerated because this reader must not invalidate
    # immutable history produced by a newer taxonomy. Known legacy gate rows
    # still receive their full structural validation below.
    for gate_type in LEGACY_GATE_TYPES:
        if gate_type not in gates:
            continue
        err = validate_entry(gate_type, gates[gate_type], where=f"gates.{gate_type}")
        if err:
            return False, err
    return True, None

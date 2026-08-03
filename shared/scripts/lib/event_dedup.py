"""Append-dedup predicates shared by the event-log writers.

``record_event.py`` is a size exception (ADR-111). Moving its by-commit and
``phase_completed`` predicates behind an injected reader preserves their exact
behavior while creating a cohesive home for append-dedup rules. Thin wrappers in
``record_event`` keep the historical ``record_event.read_events`` monkeypatch
seam intact.

The opt-in ``grade_snapshot`` rule records changes rather than regen heartbeats.
It compares only with the most recent snapshot of the same established lineage
class (``main`` or ``branch``); missing and ``unknown`` attribution never match.
Comparison uses the effective history after ``event_amended`` overlays. It is
total over durable, union-merged, hand-editable data: malformed payloads or
amendments append, as does any read containing an unrecoverable fragment. The
caller scans and appends while holding one per-checkout file lock. Manual/replay
CLI appends stay unconditional; only the automatic compliance emitter opts in.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .config import read_events

LINEAGE_CLASSES = frozenset({"main", "branch"})
UNCHANGED_GRADE = "unchanged_grade"


def lineage_class(event: Any) -> str | None:
    """Return an established tree class, never an inferred one."""
    if not isinstance(event, dict):
        return None
    lineage = event.get("lineage")
    return lineage if isinstance(lineage, str) and lineage in LINEAGE_CLASSES else None


def comparable_grade(event: Any) -> tuple[str, float] | None:
    """Return ``(grade, score)`` when the wire payload is safely comparable."""
    if not isinstance(event, dict):
        return None
    grade = event.get("grade")
    score = event.get("score")
    if not isinstance(grade, str) or not grade:
        return None
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    try:
        score = float(score)
    except (TypeError, ValueError, OverflowError):
        return None
    return (grade, score) if math.isfinite(score) else None


def last_grade_snapshot(events: list[Any], klass: str) -> dict | None:
    """Return the newest grade snapshot in ``events`` for ``klass``.

    Taking parsed events binds the reverse scan to the read performed inside the
    append lock; accepting a project root here would allow an unlocked re-read.
    """
    for event in reversed(events):
        if (isinstance(event, dict)
                and event.get("type") == "grade_snapshot"
                and lineage_class(event) == klass):
            return event
    return None


def unchanged_grade_skip(event: dict, events: list[dict]) -> dict | None:
    """Return the canonical skip payload when an established grade is unchanged."""
    klass = lineage_class(event)
    candidate = comparable_grade(event)
    if klass is None or candidate is None:
        return None
    previous = last_grade_snapshot(events, klass)
    if previous is None or comparable_grade(previous) != candidate:
        return None
    return {"reason": UNCHANGED_GRADE, "grade": candidate[0], "score": candidate[1]}


def has_commit(
    project_root: Path,
    commit: str,
    section: str | None = None,
    *,
    reader=read_events,
) -> bool:
    """Check if a work_completed event with this commit (and section) already exists.

    When *section* is provided, deduplication checks (section, commit) tuple.
    This prevents collapsing multiple sections that share the same commit hash.
    Without section, falls back to commit-only check (backwards compat).
    """
    for event in reader(project_root):
        if event.get("type") == "work_completed" and event.get("commit") == commit:
            if section is None or event.get("section") == section:
                return True
    return False


def has_phase_event(
    project_root: Path,
    phase: str,
    split_id: str | None = None,
    *,
    reader=read_events,
) -> bool:
    """Check if a phase_completed event for this ``(phase, splitId)`` already exists.

    The dedup identity is the ``(phase, splitId)`` PAIR, not ``phase`` alone. A
    multi-split pipeline phase (build/plan fan out one phase_task per split, all
    sharing the same ``phase``) records ONE phase_completed per split, so the
    tracked log keeps every split's end — the LAST split's end, which bounds the
    true per-phase span, is no longer discarded by first-wins dedup. Per-split
    duration bars derive from these; the per-phase span is min(start)..max(end).

    A single-split phase carries ``splitId=None`` → dedups by ``(phase, None)``,
    identical to the historical phase-only behavior (zero back-compat drift).
    Origin: iterate-2026-07-11-phase-completed-per-split (per-split accuracy).
    """
    for event in reader(project_root):
        if (event.get("type") == "phase_completed"
                and event.get("phase") == phase
                and event.get("splitId") == split_id):
            return True
    return False


__all__ = [
    "LINEAGE_CLASSES",
    "UNCHANGED_GRADE",
    "comparable_grade",
    "has_commit",
    "has_phase_event",
    "last_grade_snapshot",
    "lineage_class",
    "unchanged_grade_skip",
]

"""Existing append-dedup predicates extracted from ``record_event``.

``record_event.py`` is a size exception (ADR-111). Moving its by-commit and
``phase_completed`` predicates behind an injected reader preserves their exact
behavior while creating a cohesive home for append-dedup rules. Thin wrappers in
``record_event`` keep the historical ``record_event.read_events`` monkeypatch
seam intact.
"""

from __future__ import annotations

from pathlib import Path

from .config import read_events


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
    "has_commit",
    "has_phase_event",
]

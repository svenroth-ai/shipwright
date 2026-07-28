"""How a phase-task status is classified, in one place.

Owner of the vocabulary: ``shared/schemas/run_config.v2.schema.json`` →
``$defs.PhaseTaskStatus`` (``backlog``, ``awaiting_launch``, ``in_progress``,
``done``, ``failed``, ``skipped``).

Everything the handoff says about a phase — is it banked, is it mid-flight, is it
dead, may the dispatch pointer call it live — comes from ONE bucketed map here.
An earlier version kept a verdict map beside four independent status literals; the
drift test then forced only the map, so the cheapest way to make it green for a new
status was to add a verdict and nothing else, leaving the newcomer out of the tally,
out of every bullet, and non-terminal for the pointer line. That silently rebuilt
the very defects it was meant to prevent. Deriving every set from the one map means
adding a key IS classifying it, and a bucket nobody defined is a ``KeyError`` at
import rather than a wrong sentence in someone's handoff.
"""
from __future__ import annotations

# How each status renders once bucketed. A bucket name with no entry here is a
# KeyError at import — see _STATUS_BUCKETS.
_BUCKET_VERDICTS: dict[str, str] = {
    "finished": "yes",
    "interrupted": "**no — interrupted**",
    "failed": "**no — failed**",
    "pending": "no",
}

# The ONE place a status is classified, and the source of EVERY set below.
#
# An earlier version kept a verdict map beside four independent status literals.
# The drift test then forced only the map, so the cheapest way to make it green
# for a new status was to add a verdict and nothing else — leaving the newcomer
# out of the tally, out of every bullet, and non-terminal for the pointer line.
# That silently rebuilt the exact defects R5 and R2 were filed for. Deriving all
# four sets from one bucketed map means adding a key IS classifying it, and a
# bucket nobody defined fails at import rather than at the next handoff.
_STATUS_BUCKETS: dict[str, str] = {
    "done": "finished",
    "skipped": "finished",
    "in_progress": "interrupted",
    "failed": "failed",
    "backlog": "pending",
    "awaiting_launch": "pending",
}
_STATUS_VERDICTS: dict[str, str] = {
    status: _BUCKET_VERDICTS[bucket] for status, bucket in _STATUS_BUCKETS.items()
}


def _bucket(name: str) -> frozenset[str]:
    return frozenset(s for s, b in _STATUS_BUCKETS.items() if b == name)


FINISHED_STATUSES = _bucket("finished")
FAILED_STATUSES = _bucket("failed")
INTERRUPTED_STATUSES = _bucket("interrupted")
KNOWN_STATUSES = frozenset(_STATUS_BUCKETS)

# A pointer resting on one of these has nothing in flight, whatever the attempt
# counter says — `recover_single_session` deliberately leaves the pointer and the
# counter alone for a terminal force-status.
TERMINAL_STATUSES = FINISHED_STATUSES | FAILED_STATUSES

# Back-compat aliases for the two singular names the predecessor exported.
INTERRUPTED_STATUS = "in_progress"
FAILED_STATUS = "failed"




def status_of(task: dict) -> str | None:
    """The task's status as a plain string, or ``None`` if it is not one.

    Everything downstream compares against a frozenset, and a malformed producer
    can put a list or dict here — ``x in frozenset`` then raises
    ``TypeError: unhashable type``. The Stop hook's outer ``except Exception``
    would turn that into a SILENTLY skipped handoff, which is worse than a crash
    for a document whose whole job is telling a person where they are.
    """
    status = task.get("status")
    return status if isinstance(status, str) else None


def finished_verdict(status: str | None) -> str:
    """The Finished? cell. ``None`` means the producer wrote something we could not
    read, so the honest answer is "unknown" — a categorical "no" would assert
    not-finished about a status the renderer just admitted it could not parse."""
    if status is None:
        return "unknown"
    return _STATUS_VERDICTS.get(status, "no")

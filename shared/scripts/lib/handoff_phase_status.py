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

from typing import Any

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


def phase_tasks_progress(run_config: dict[str, Any]) -> tuple[str | None, set[str]]:
    """``(current_phase, completed_phases)`` derived from ``phase_tasks[]``.

    The single implementation shared by ``shared/scripts/lib/state.py``,
    ``shared/scripts/hooks/generate_handoff_on_stop.py`` and
    ``shared/scripts/hooks/suggest_iterate.py`` (campaign
    p4-04-retire-write-once-steps, sub-iterate s3 code review — the three
    callers had each carried a byte-for-byte copy).

    ``phase_tasks[]`` is the SOLE authority for progress. The write-once
    ``current_step``/``completed_steps`` fields, and every writer of them,
    are retired (campaign p4-04-retire-write-once-steps, sub-iterate s5):
    the v1 ``update_step`` path now advances ``phase_tasks[]`` directly, so
    no caller falls back to those fields any more — ``None`` current + an
    empty completed set mean only "no ``phase_tasks[]`` evidence at all"
    (an absent or malformed array; there was never anything else to read).
    A phase counts as "current" the moment it has ANY ``phase_tasks[]``
    entry that isn't finished yet — including one still
    ``backlog``/``awaiting_launch`` (queued, not yet claimed), not only an
    active (``in_progress``/``failed``) one. External plan review flagged an
    earlier version that required an ACTIVE status: a run mid-transition
    (previous phase done, successor task materialized but not yet claimed)
    would then read as "no confident signal" — a regression this module no
    longer has a fallback to hide behind.

    A phase can hold MULTIPLE entries when it is split (``plan``/``build``
    under ``splits_frozen``): it counts as complete only once every one of
    them is ``done``/``skipped`` — mirrors
    ``plugins/shipwright-compliance/scripts/lib/mermaid.py``'s
    ``_phase_tasks_status`` per-phase aggregation for the completed-phases
    half (that module duplicates rather than imports this one: it is
    plugin-side and importing a shared-tree module from there would be the
    ADR-045 cross-plugin ``lib``-namespace collision this module's own
    callers are not subject to, since they already live under
    ``shared/scripts/``).

    Doubt review, sub-iterate s3: on a genuinely driven (v2) run,
    ``recover_phase_task(force_status="skipped")`` — the operator's manual
    escape hatch, ``plugins/shipwright-run/scripts/lib/phase_task_lifecycle.py``
    — can terminalize the frontier task WITHOUT planning a successor (unlike
    the normal ``complete_phase_task`` path, which always plans one under the
    same lock). That persists a state where every PRESENT ``phase_tasks[]``
    entry is finished but the pipeline is not fully covered and no entry
    exists yet for the true next phase — indistinguishable, by shape alone,
    from a hybrid/standalone config where a later phase is being run
    ad hoc, uncorrelated with pipeline order (an already-accepted,
    already-tested contract from sub-iterate s1 that must fall through to
    each caller's own heuristic/v1 fallback, not assume pipeline order).
    ``schemaVersion`` is the discriminator: ``config_factory`` writes it on
    EVERY driven v2 run and never on a v1-only/standalone config, so it is
    only when ``schemaVersion`` is present that "first pipeline phase not
    yet completed" is derived as ``current`` even without its own
    ``phase_tasks[]`` entry — closing the operator-recovery gap without
    touching the untagged hybrid-config case sub-iterate s1's own tests pin.
    """
    tasks = run_config.get("phase_tasks")
    if not isinstance(tasks, list):
        return None, set()

    by_phase: dict[str, list[str | None]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        phase = task.get("phase")
        if isinstance(phase, str):
            by_phase.setdefault(phase, []).append(status_of(task))

    completed = {
        phase for phase, statuses in by_phase.items() if all(s in FINISHED_STATUSES for s in statuses)
    }
    pipeline_order = run_config.get("pipeline") or list(by_phase)
    current = next(
        (
            phase
            for phase in pipeline_order
            if phase in by_phase and phase not in completed
        ),
        None,
    )
    if current is None and by_phase and run_config.get("schemaVersion"):
        current = next((phase for phase in pipeline_order if phase not in completed), None)
    return current, completed


def phase_tasks_has_usable_entries(run_config: dict[str, Any]) -> bool:
    """True iff EVERY entry in a non-empty ``phase_tasks[]`` is one
    :func:`phase_tasks_progress` can classify — a dict carrying a string
    ``phase`` and a recognized ``status`` (:data:`KNOWN_STATUSES`, via
    :func:`status_of`).

    ``all``, not ``any``: a list mixing one valid entry with one malformed
    entry (e.g. ``{"phase": "design"}`` with no ``status``) is NOT usable —
    trusting it would silently drop the malformed phase's real state rather
    than falling back to ``completed_steps`` for it. Full rationale for this
    predicate (including why it exists as a standalone export, not just
    inlined in :func:`completed_phases_with_fallback`) and its review
    history: campaign p4-04-retire-write-once-steps, sub-iterate s4 ADR.
    """
    tasks = run_config.get("phase_tasks")
    return isinstance(tasks, list) and bool(tasks) and all(
        isinstance(task, dict)
        and isinstance(task.get("phase"), str)
        and status_of(task) in KNOWN_STATUSES
        for task in tasks
    )


def completed_phases(run_config: dict[str, Any]) -> set[str]:
    """Completed phase names, from ``phase_tasks[]`` alone.

    Empty when :func:`phase_tasks_has_usable_entries` says the array is
    absent, malformed, empty, or partially malformed — "no confident
    evidence" now means "no completed phases", not a cue to consult the
    write-once ``completed_steps`` (retired campaign
    p4-04-retire-write-once-steps, sub-iterate s5 — every writer advances
    ``phase_tasks[]`` directly, so it is always the complete picture, and
    there is no other source left to fall back to).

    A phase counted here folds ``done`` AND ``skipped`` together (via
    ``FINISHED_STATUSES``), matching ``completed_steps``'s own pre-retirement
    semantics.

    Shared by design_checks.py / compliance_compliance.py /
    convert_configs_to_events.py — one function, one contract, instead of
    three call sites re-deriving the same rule. Full rationale and review
    history: campaign p4-04-retire-write-once-steps, sub-iterate s4 ADR
    (introduced this shape as a completed_steps-fallback; s5's ADR records
    the fallback's removal).
    """
    if not phase_tasks_has_usable_entries(run_config):
        return set()
    return phase_tasks_progress(run_config)[1]

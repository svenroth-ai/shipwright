"""Layer 1 — is a phase part of THIS project's active lifecycle?

Owns the whole applicability gate: :func:`load_engagement_inputs` (read the
inputs), :func:`phase_is_engaged` (the predicate the Stop-time audit gates on),
and the v2 ``phase_tasks[]`` vocabulary the predicate now consults.

``current_step`` / ``completed_steps`` are write-once on an orchestrator-driven
run — ``config_factory`` stamps them at creation and the v2 lifecycle never
advances them (only the v1 ``update_step`` path does, and it is inert on a driven
run). ``phase_tasks[]`` is the authority that does not go stale, so both
Phase-Quality readers consult it: :func:`phase_is_engaged` for which phases the
Stop-time audit covers, and :func:`~._resolution.resolve_source` for the
orchestrator/standalone stamp.

Split out of ``_triage_bundle`` so a run-config shape predicate does not live in
the triage-bundle module that ``_resolution`` would otherwise have to reach into
for it. Imports nothing from this package, so the edge stays one-way and acyclic.

**Why the v1 fields are still consulted alongside this.**
:func:`phase_is_engaged` ORs the two sources rather than swapping to v2.
The v1 shape is still actively written (``shipwright-project``,
``shipwright-adopt``, and the v1 ``update_step`` path), and a phase completed
standalone before ``/shipwright-run`` appears as ``skipped`` in ``phase_tasks[]``
while living in ``completed_steps`` — so a v2-only read would silently audit
FEWER phases, the one direction Phase-Quality must never move in. Retiring the v1
fields is a campaign blocked on ~9 other readers (triage ``trg-8d52a965``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_log import resolve_events_path  # noqa: E402
from lib.handoff_phase_status import status_of  # noqa: E402
from lib.jsonl_records import read_jsonl_records  # noqa: E402

# Does a v2 ``phase_tasks[]`` status mean "this phase actually ran, or is running"?
#
# An explicit decision PER STATUS, mirroring ``handoff_phase_status._STATUS_BUCKETS``:
# adding a status to the schema means CLASSIFYING it here, and the drift test
# ``test_every_known_status_is_classified`` fails on one that is left out. A bare
# ``frozenset`` of the engaged three would have drifted silently in the one direction
# Phase-Quality forbids — an unclassified newcomer reads as not-engaged, its Tier-1
# FAILs get rewritten to SKIP, and the audit covers FEWER phases with no test red.
_STATUS_ENGAGES: dict[str, bool] = {
    "in_progress": True,       # running right now
    "done": True,              # ran to completion
    "failed": True,            # ran and broke — the most audit-worthy state there is
    "backlog": False,          # never claimed
    # The two below mean "did not run" ONLY as an initial state. `recover_phase_task`
    # can force a task that DID run back to `awaiting_launch`, or retire it as
    # `skipped`; `config_factory` also marks a phase completed STANDALONE as
    # `skipped`. Status alone would leave all three unaudited, and on a driven run
    # the frozen `completed_steps` cannot rescue them — so execution history is
    # consulted too, see :func:`_task_has_run`.
    "awaiting_launch": False,
    "skipped": False,
}

ENGAGED_TASK_STATUSES = frozenset(s for s, engaged in _STATUS_ENGAGES.items() if engaged)


def _task_has_run(task: dict) -> bool:
    """``True`` iff this phase task has executed at least once.

    ``executionCount`` is bumped by ``claim_phase_task`` and deliberately NOT reset
    by ``recover_phase_task`` (which nulls ``startedAt`` but preserves the count),
    so it is the one field that survives a status rewrite. Schema-required, but
    read defensively: a malformed value must not raise inside a Stop hook.
    """
    count = task.get("executionCount")
    return isinstance(count, int) and not isinstance(count, bool) and count > 0


def has_phase_tasks(cfg: dict | None) -> bool:
    """``True`` iff *cfg* carries a ``phase_tasks[]`` holding at least one entry.

    Presence of the array is what identifies an orchestrator-DRIVEN run:
    ``config_factory`` materializes it at run creation and ``phase_task_lifecycle``
    is its only writer thereafter. Never raises — a malformed array is simply
    "no v2 evidence".

    Deliberately laxer than ``phase_invocation_mode.read_run_config``, which
    REJECTS the whole config when any entry is a non-dict. That resolver is an
    authority deciding whether a phase may write pipeline state, so it fails
    CLOSED; this one only stamps a telemetry label, so it fails OPEN and reads
    what it can.
    """
    if not isinstance(cfg, dict):
        return False
    tasks = cfg.get("phase_tasks")
    return isinstance(tasks, list) and any(isinstance(t, dict) for t in tasks)


def engaged_via_phase_tasks(phase: str, cfg: dict) -> bool:
    """``True`` iff a v2 ``phase_tasks[]`` entry shows *phase* ran or is running.

    A task counts when its STATUS says it ran, OR when its execution history does
    (:func:`_task_has_run`) — the latter catches a task rewritten by
    ``recover_phase_task`` to a status that normally means "never started".

    Reads the status through ``status_of``, never ``t.get("status")`` directly: a
    malformed producer can put a list or dict there, and ``x in frozenset`` hashes
    its operand, so a raw read raises ``TypeError: unhashable type``. That would
    escape through :func:`~._triage_bundle.collect_in_scope_fails` into the Stop
    hook's outer ``except`` and silently skip the backlog emit for that Stop — the
    same defect ``handoff_phase_status.status_of`` was written for.
    """
    tasks = cfg.get("phase_tasks")
    if not isinstance(tasks, list):
        return False
    return any(
        isinstance(t, dict)
        and t.get("phase") == phase
        and (status_of(t) in ENGAGED_TASK_STATUSES or _task_has_run(t))
        for t in tasks
    )


def load_engagement_inputs(project_root: Path) -> tuple[dict | None, list[dict]]:
    """Read run-config + event log for the engagement predicate (FAIL-OPEN).

    Returns ``(cfg, events)``. ``cfg`` is ``None`` when
    ``shipwright_run_config.json`` is missing or malformed — callers MUST
    treat ``cfg is None`` as "cannot determine engagement → engaged" so a
    read error never silently suppresses alerts (AC-1b).
    """
    cfg: dict | None = None
    cfg_path = project_root / "shipwright_run_config.json"
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg = data
        except (json.JSONDecodeError, OSError):
            cfg = None

    events: list[dict] = []
    ev_path = resolve_events_path(project_root)  # SSOT accessor (worktree-aware)
    if ev_path.exists():
        try:
            # Record-boundary recovery via the shared SSoT, matching
            # ``_resolution.resolve_run_id``: a merge=union merge can leave two
            # records on one physical line, and a per-line ``json.loads`` drops
            # BOTH. Here that silently UN-engages a phase whose ``phase_completed``
            # event was the only evidence it ran — audit-fewer, the one direction
            # this module forbids (iterate-2026-07-20-events-record-boundary-remainder).
            events = [o for o in read_jsonl_records(ev_path).records if isinstance(o, dict)]
        except OSError:
            events = []
    return cfg, events


def phase_is_engaged(phase: str, cfg: dict | None, events: list[dict]) -> bool:
    """Whether ``phase`` is part of THIS project's active lifecycle.

    Engaged iff ANY of:

    * a ``phase_completed`` event, or a ``work_completed`` event with
      ``source == phase``, exists in the event log; OR
    * ``cfg.status == "complete"`` AND ``phase == "iterate"`` (iterate is the
      always-on maintenance phase of a finished project); OR
    * ``cfg.status != "complete"`` AND EITHER a v2 ``phase_tasks[]`` entry shows
      ``phase`` ran, OR (v1) ``phase ∈ completed_steps`` / ``== current_step``.

    The v2 and v1 halves are OR-ed, never swapped (see the module docstring),
    both behind ``status != "complete"`` so a finished run stays iterate-only
    (AC-2). FAIL-OPEN: ``cfg is None`` → engaged. Status casing is normalized.

    ``complete`` is the ONLY status that closes a run here, deliberately. A run
    parked in ``needs_validation`` or ``failed`` has not finished, so every phase
    that ran stays audited — that is the "audit MORE" direction, and those are the
    runs where an open Tier-1 FAIL matters most. It does mean such a run keeps
    auditing those phases in later sessions until it is completed or recovered.
    """
    if cfg is None:
        return True  # AC-1b — cannot determine → never suppress

    for e in events or []:
        if not isinstance(e, dict):
            continue
        etype = e.get("type")
        if etype == "phase_completed" and (e.get("source") == phase or e.get("phase") == phase):
            return True
        if etype == "work_completed" and e.get("source") == phase:
            return True

    status = str(cfg.get("status") or "").strip().lower()
    if phase == "iterate" and status == "complete":
        return True
    if status != "complete":
        if engaged_via_phase_tasks(phase, cfg):
            return True
        completed = cfg.get("completed_steps")
        if isinstance(completed, list) and phase in completed:
            return True
        if phase == cfg.get("current_step"):
            return True
    return False


__all__ = [
    "ENGAGED_TASK_STATUSES",
    "engaged_via_phase_tasks",
    "has_phase_tasks",
    "load_engagement_inputs",
    "phase_is_engaged",
]

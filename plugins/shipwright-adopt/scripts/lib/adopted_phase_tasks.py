"""Build ``phase_tasks[]`` entries for phases established at adoption time.

Split out of ``config_writer.py`` (grandfathered at its own bloat ceiling) —
a cohesive, single-purpose helper, not a premature abstraction: this is the
one place that knows the ``PhaseTask`` shape adopt seeds.

Campaign p4-04-retire-write-once-steps, sub-iterate s2: adopt seeds
``phase_tasks[]`` so future readers moving off ``completed_steps`` /
``phase_history`` still see an adopted repo as having its pre-adoption
phases accounted for, not skipped.
"""

from __future__ import annotations

import uuid
from typing import Any

# Mirrors schema `run_config.v2.schema.json`'s `$defs.Phase` enum and the
# `slashCommand` pattern `^/shipwright-(project|design|plan|build|test|
# security|changelog|deploy)$`. Not loaded from the schema file: this plugin
# is deliberately jsonschema-dependency-free (see `enrichment_schema.py`).
_VALID_PHASES = frozenset({
    "project", "design", "plan", "build", "test", "security", "changelog", "deploy",
})


def new_phase_task_id() -> str:
    """``ptk-<hex>`` id shape (schema ``PhaseTaskId`` pattern
    ``^ptk-[0-9a-f]{4,}$``), mirroring
    ``plugins/shipwright-run/scripts/lib/phase_task_lifecycle.py``'s
    ``_new_phase_task_id``. Not imported from there: that plugin's own
    ``lib`` package would collide with this plugin's ``lib`` namespace
    under the shared loader (ADR-045) — three lines isn't worth a
    cross-plugin loader for.
    """
    return "ptk-" + uuid.uuid4().hex[:8]


def build_adopted_phase_task(step: str, *, now: str) -> dict[str, Any]:
    """Build one ``phase_tasks[]`` entry for a phase established at adoption
    time — never run through the phase-task lifecycle, but not outstanding
    either.

    ``status`` is a TERMINAL ``PhaseTaskStatus`` (``done``/``skipped``, the
    same split ``write_run_config``'s ``phase_history`` outcome already
    makes: ``test`` reads ``adopted-skipped`` there because adoption never
    ran a test suite, everything else reads ``adopted``) so
    ``phase_tasks[]`` readers such as
    ``plugins/shipwright-compliance/scripts/lib/mermaid.py``'s
    ``_phase_tasks_status`` (finished-status set) render the phase as
    complete rather than pending — AC1, "does not render as having skipped
    phases". ``establishedAtAdoption: True`` is the extra, additive marker
    (schema ``PhaseTask.additionalProperties`` is ``true``) that keeps an
    adopted-in entry visibly distinct from one an actual phase-runner
    executed — AC2, "adopted-in and executed phases are distinguishable".

    Raises ``ValueError`` for a *step* outside the schema's ``Phase`` enum —
    ``write_all(..., completed_steps=[...])`` is a public keyword parameter, so
    an out-of-vocabulary value (a typo, or a caller-supplied custom list) would
    otherwise silently mint an entry violating both `$defs.Phase` and the
    ``slashCommand`` pattern (caught in review at 3f-bis, campaign
    p4-04-retire-write-once-steps).
    """
    if step not in _VALID_PHASES:
        raise ValueError(
            f"build_adopted_phase_task: {step!r} is not a valid Phase "
            f"({sorted(_VALID_PHASES)})",
        )
    status = "skipped" if step == "test" else "done"
    return {
        "phaseTaskId": new_phase_task_id(),
        "phase": step,
        "splitId": None,
        "sessionUuid": str(uuid.uuid4()),
        "version": 1,
        "status": status,
        "title": f"{step.replace('-', ' ').title()} (established at adoption)",
        "description": (
            "Seeded by /shipwright-adopt: this phase pre-dates adoption and was "
            "never run through the phase-task lifecycle. Not outstanding."
        ),
        "slashCommand": f"/shipwright-{step}",
        "prerequisites": [],
        "claimedBySessionUuid": None,
        "claimAttemptedAt": None,
        "executionCount": 0,
        "createdAt": now,
        "awaitingLaunchAt": None,
        "startedAt": None,
        "completedAt": now,
        "result": {"ok": True, "establishedAtAdoption": True},
        "errors": [],
        "establishedAtAdoption": True,
    }

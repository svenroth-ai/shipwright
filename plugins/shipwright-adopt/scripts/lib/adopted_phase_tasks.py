"""Build ``phase_tasks[]`` entries for phases established at adoption time.

Split out of ``config_writer.py`` (grandfathered at its own bloat ceiling) —
a cohesive, single-purpose helper, not a premature abstraction: this is the
one place that knows the ``PhaseTask`` shape adopt seeds.

Campaign p4-04-retire-write-once-steps, sub-iterate s2: adopt seeds
``phase_tasks[]`` so future readers moving off ``completed_steps`` /
``phase_history`` still see an adopted repo as having its pre-adoption
phases accounted for, not skipped.

Sub-iterate s2b: s2's seeding only fires at NEW-adoption time
(``write_run_config``, called once by ``write_all``), so a repo adopted
BEFORE s2 landed has ``completed_steps`` and no ``phase_tasks[]`` on disk at
all. :func:`backfill_missing_phase_tasks` is that gap's owner — it computes
the same entries against an EXISTING config, callable by
``plugins/shipwright-adopt/scripts/tools/backfill_phase_tasks.py`` against a
project already on disk (verified against a real pre-2026-09 adopted
repo — see that tool's docstring).
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


def backfill_missing_phase_tasks(
    run_config: dict[str, Any], *, now: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Compute the ``phase_tasks[]`` backfill for an already-adopted config.

    Pure function — no I/O; the CLI wrapper
    (``scripts/tools/backfill_phase_tasks.py``) owns reading/writing the
    file on disk. Returns ``(updated_run_config, added_phases, skipped_phases)``:

    * ``updated_run_config`` is a NEW dict — *run_config* itself is never
      mutated, so a caller that fails to persist the result is not left
      with a silently-changed in-memory copy.
    * ``added_phases`` lists the phases a ``phase_tasks[]`` entry was
      created for, in ``completed_steps`` order.
    * ``skipped_phases`` lists ``completed_steps`` entries that are not a
      valid schema ``Phase``, or not even a string (old configs never
      validated this list) — not fatal, just unrepresentable as a
      ``PhaseTask``.

    Guarded to ADOPTED configs only — ``adoption`` must be present AND a
    JSON object. An orchestrator-driven config missing ``phase_tasks[]``
    for some other reason is not this gap: shipwright-adopt is the one
    writer this function backfills for, and inventing entries for a run it
    never observed would misrepresent that run. A malformed ``adoption``
    (e.g. ``null``, from hand-edited or corrupted config) is treated the
    same as absent — no-op, never guessed at (external code review,
    sub-iterate s2b: a bare ``.get()`` on a non-dict ``adoption`` would
    otherwise crash the caller).

    A ``phase_tasks[]`` that is PRESENT but not a list is left entirely
    untouched rather than silently discarded and overwritten with a fresh
    array — malformed data is a signal to stop, not a green light to
    replace it (external code review, s2b).

    ``completed_steps`` duplicates are folded to their first occurrence —
    the "one entry per phase" contract this function documents must hold
    even when the source list itself repeats a phase (external code
    review, s2b: an unfolded scan would otherwise mint two entries for one
    phase on the very first backfill).

    Idempotent by construction: a phase already represented in
    ``phase_tasks[]`` — by its ``phase`` key, regardless of shape or who
    wrote it — is left alone. Running this twice on the same config adds
    nothing the second time (AC2), and a config that mixes seeded
    adoption entries with later REAL orchestrator-driven ones only has its
    gap filled, never a real entry touched. A no-op path (nothing to add)
    returns *run_config* itself, the same object the caller passed in, not
    a copy — there is nothing to protect a copy FROM when no field is ever
    written; "never mutated" above is about in-place writes, not about
    identity on every return path (PR-review comment, s2b PR #701).

    ``test`` backfills as ``skipped``, every other phase as ``done`` — the
    same phase-NAME-keyed split ``write_run_config`` already makes for
    ``phase_history[phase].outcome`` (``adopted-skipped`` vs ``adopted``),
    via the shared ``build_adopted_phase_task``. Both are keyed by the
    identical rule, so a backfilled entry's status always agrees with the
    config's own recorded outcome for any config this codebase produced —
    not derived independently, and so nothing to reconcile against
    ``phase_history`` at call time.
    """
    adoption = run_config.get("adoption")
    if not isinstance(adoption, dict):
        return run_config, [], []
    completed_steps = run_config.get("completed_steps")
    if not isinstance(completed_steps, list):
        return run_config, [], []

    existing = run_config.get("phase_tasks")
    if "phase_tasks" in run_config and not isinstance(existing, list):
        return run_config, [], []
    existing_list = existing if isinstance(existing, list) else []
    # `t.get("phase")` on an already-present PhaseTask is trusted nowhere
    # else in this codebase, and a hand-edited or corrupted config can carry
    # a malformed entry whose "phase" is itself a list or dict -- UNHASHABLE,
    # so including it in this set-comprehension would raise TypeError before
    # the function ever reaches its own step-by-step guard below (PR-review
    # gate, s2b PR #701: a case the doubt-review's completed_steps-side fix
    # did not cover -- this is the SAME hazard on the existing-entries side).
    # A malformed existing entry is simply not represented in `seen`; its own
    # slot in `existing_list` is untouched either way (this function only
    # ever appends, never rewrites `existing_list` itself).
    seen = {
        t.get("phase")
        for t in existing_list
        if isinstance(t, dict) and isinstance(t.get("phase"), str)
    }

    to_add: list[str] = []
    skipped: list[Any] = []
    for step in completed_steps:
        # A non-string entry (a stray dict/list from a hand-edited or
        # corrupted config -- "old configs never validated this list", see
        # the docstring) is UNHASHABLE, so `step in seen` / `seen.add(step)`
        # below would raise TypeError instead of the "skipped, not fatal"
        # behaviour this function promises (doubt-reviewer, s2b). Caught
        # here, before it ever reaches the hash check.
        if not isinstance(step, str):
            skipped.append(step)
            continue
        if step in seen:
            continue
        seen.add(step)
        to_add.append(step)
    if not to_add:
        return run_config, [], skipped

    new_tasks: list[dict[str, Any]] = []
    for step in to_add:
        try:
            new_tasks.append(build_adopted_phase_task(step, now=now))
        except ValueError:
            skipped.append(step)

    if not new_tasks:
        return run_config, [], skipped

    updated = dict(run_config)
    updated["phase_tasks"] = [*existing_list, *new_tasks]
    added = [t["phase"] for t in new_tasks]
    return updated, added, skipped

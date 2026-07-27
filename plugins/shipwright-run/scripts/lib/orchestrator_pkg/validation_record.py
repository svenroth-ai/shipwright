"""Phase-gate evidence for the v1 step-advance path.

FR-01.01 (E): *"Given a person decides to go ahead regardless, when the phase is
marked finished anyway, then what was overridden and why is recorded — so
afterwards 'passed its checks' and 'was waved through' can still be told apart."*

Before this module ``update_step`` gated completion behind ``not force``::

    if not force and not is_standalone:
        valid, issues = validate_phase(step, project_root)

so with ``--force`` the validator **did not run at all**. Nothing knew what the
gate would have said, nothing recorded that an override happened or why, and
``inform``-level notes were dropped on that path too. Afterwards ``completed_steps``
said only *"this phase completed"* — a phase that passed cleanly and a phase that
was waved through left byte-identical state.

The rule requiring a person to be asked already existed (``status:
"needs_validation"``). What was missing is that the person's answer landed
anywhere. This module owns the three pieces that fixes:

    run_phase_gate             run the check, ALWAYS, and never let it wedge the run
    record_inform_notes        the non-blocking notes (moved from step_planning)
    record_validation_override the durable "what was overridden, and why" entry

Kept out of ``step_planning`` deliberately: that module is at 245 of its 300-LOC
budget, and these are pure functions over a config dict — testable without the
advisory lock, the compliance subprocess, or a pipeline.

Scope: this is the **v1** completion path (``completed_steps``), which serves
standalone / legacy / adopted runs. The v2 driven path
(``single-session-apply`` → ``phase_task_lifecycle``) has no ``--force`` and is
untouched.
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .critical_gates import (
    _collect_critical_gate_issues,
    _enforce_critical_gates_enabled,
    _read_latest_phase_quality_finding,
)

# Key under which the durable override log lives in shipwright_run_config.json.
# Declared in shared/schemas/run_config.v2.schema.json next to validation_issues.
VALIDATION_OVERRIDES_KEY = "validation_overrides"
VALIDATION_OVERRIDES_DROPPED_KEY = "validation_overrides_dropped"

# Retention. Generous on purpose: these records are the ONLY durable thing that
# distinguishes "passed its checks" from "was waved through", so they are not
# cheap to discard. An eviction is never silent — see record_validation_override.
MAX_VALIDATION_OVERRIDES = 200

# Prefix on the synthetic issue raised when the validator itself blew up.
GATE_ERROR_PREFIX = "[gate-error]"


def _gate_error(step: str, exc: BaseException, what: str) -> dict[str, Any]:
    """One ask-level issue standing in for a gate that blew up.

    The exception is swallowed and never re-raised, so without the traceback on
    stderr the frames would exist NOWHERE — the record stays readable but the
    underlying bug becomes undebuggable. Before the gate ran under force, the
    same bug produced a full traceback out of the CLI; keep that for the operator
    while the durable record stays a single compact line.
    """
    print(
        f"[validation_record] {what} for step {step!r} raised — "
        f"recording a {GATE_ERROR_PREFIX} finding:\n{traceback.format_exc()}",
        file=sys.stderr,
    )
    return {
        "severity": "ask",
        "message": (
            f"{GATE_ERROR_PREFIX} {what} for '{step}' raised "
            f"{type(exc).__name__}: {exc}"
        ),
    }


def run_phase_gate(
    project_root: Path, step: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Run the phase's own validation plus the opt-in Phase-Quality critical gate.

    Returns ``(ask_issues, inform_issues, checked)``. Read-only: touches no config
    and holds no lock, so the caller runs it OUTSIDE ``run_config_lock`` exactly
    as the inline version did (audit WP2/F11).

    ``checked`` is False when **no validator exists for this step**.
    ``validate_phase`` returns ``(True, [])`` for an unknown step — indistinguishable
    at the call site from a clean pass — and ``security`` is an accepted ``--step``
    with no ``_VALIDATORS`` entry. Reporting that as a pass minted a durable record
    asserting a gate had been satisfied where no gate exists; the caller uses this
    flag to record ``not_checked`` instead.

    ``validate_phase`` is imported lazily INSIDE this function on purpose:
    ``test_orchestrator.py`` patches ``phase_validators.validate_phase`` — the
    module attribute — which a module-level ``from ... import`` would have
    already bound past. Do not hoist it.

    A validator that RAISES must not wedge the run. Before force ran the gate, a
    broken validator was escapable precisely because force skipped it; now an
    unhandled exception would leave no way to complete the phase at all. So a
    crash becomes an ask-level issue: the unforced path pauses fail-closed with a
    readable reason, and the forced path completes with the crash recorded as part
    of what was overridden.

    The two failure domains are guarded SEPARATELY. A crash in the Phase-Quality
    lookup must not discard the findings ``validate_phase`` already produced —
    replacing them with a bare gate-error made the override record misstate what
    was actually overridden, which is the one thing it exists to get right.
    """
    ask_issues: list[dict[str, Any]] = []
    inform_issues: list[dict[str, Any]] = []
    checked = True

    try:
        from phase_validators import _VALIDATORS, validate_phase  # noqa: WPS433

        # Reaching for a private name, deliberately. Code review preferred a
        # public `has_validator()` predicate on phase_validators — correct in
        # principle, but that file is grandfathered at 495 LOC and the addition
        # ratcheted its bloat baseline. Cutting unrelated lines to make room
        # would game the metric. The coupling is covered by
        # test_run_phase_gate_reports_whether_a_validator_existed, which fails
        # if _VALIDATORS is ever refactored away.
        checked = step in _VALIDATORS
        _valid, issues = validate_phase(step, project_root)
        ask_issues = [i for i in issues if i.get("severity") == "ask"]
        inform_issues = [i for i in issues if i.get("severity") == "inform"]
    except Exception as exc:  # noqa: BLE001 — a broken gate must not wedge the run
        return [_gate_error(step, exc, "phase validation")], [], checked

    # Phase-Quality critical-gate (plan § 4.4) — opt-in via
    # SHIPWRIGHT_ENFORCE_CRITICAL_GATES=1, default OFF. Pulls the most recent
    # per-phase finding JSON written by the Stop hook and promotes any W5/W6/W7
    # FAIL into an ask-level issue. Its own try: a failure here APPENDS, never
    # replaces.
    try:
        if _enforce_critical_gates_enabled():
            finding = _read_latest_phase_quality_finding(project_root, step)
            if finding:
                ask_issues.extend(_collect_critical_gate_issues(finding))
    except Exception as exc:  # noqa: BLE001
        ask_issues.append(_gate_error(step, exc, "the Phase-Quality critical gate"))

    return ask_issues, inform_issues, checked


def normalise_override_reason(reason: str | None) -> str:
    """Return the reason to record, or raise when there is nothing to record.

    Enforced in the library, not only at the CLI: a headless script or another
    plugin calling ``update_step(..., force=True)`` directly would otherwise
    reopen exactly the gap this gate exists to close. Whitespace-only is treated
    as absent, so ``--force-reason "   "`` is refused too.
    """
    text = (reason or "").strip()
    if not text:
        raise ValueError(
            "force=True requires a reason. An override that records no reason is "
            "the gap FR-01.01 exists to close — afterwards 'passed its checks' "
            "and 'was waved through' must still be tellable apart. Pass "
            'force_reason="<why>" (CLI: --force-reason "<why>").'
        )
    return text


def record_inform_notes(
    config: dict[str, Any], step: str, inform_issues: list[dict[str, Any]],
) -> None:
    """Record inform-level validation notes (non-blocking), in place, without
    duplicating a note that is already there.

    Dedup is on ``(step, message)`` — NOT on ``step`` alone. The gate now re-runs
    under force, so the documented pause -> ``--force`` flow produced the same
    inform issue twice; ``validation_notes`` has no retention cap and
    ``update_build_dashboard`` renders one line per entry into a TRACKED artifact,
    so appending grew the config and the dashboard with visible duplicates.

    But wiping every note for the step would lose real findings: the split loop
    re-enters ``plan`` / ``build`` once per split and ``_validate_plan`` validates
    only the CURRENT split, so plan/01's notes describe different artifacts than
    plan/02's and are not superseded by them. Matching on the message keeps
    distinct findings from every split and drops only the exact re-append.
    """
    fresh = [{"step": step, **i} for i in inform_issues]
    seen = {(n.get("step"), n.get("message")) for n in fresh}
    kept = [
        n for n in (config.get("validation_notes") or [])
        if not (isinstance(n, dict) and (n.get("step"), n.get("message")) in seen)
    ]
    if kept or fresh:
        config["validation_notes"] = kept + fresh
    else:
        config.pop("validation_notes", None)


def record_validation_override(
    config: dict[str, Any],
    step: str,
    *,
    reason: str,
    ask_issues: list[dict[str, Any]],
    inform_issues: list[dict[str, Any]],
    checked: bool = True,
) -> dict[str, Any]:
    """Append one durable "this phase was completed under override" record, in place.

    ``waived`` is the load-bearing field. ``True`` means the gate FOUND ask-level
    issues and a person decided to go ahead anyway; ``overridden_issues`` carries
    what those were, verbatim. A forced completion over a CLEAN gate records
    ``waived: False`` / ``gate_result: "pass"`` — force was used but nothing was
    actually waived, which is a different fact and worth keeping separate.

    ``gate_result`` has THREE values, not two. ``checked=False`` (no validator
    exists for this step — ``security`` is an accepted ``--step`` with no
    ``_VALIDATORS`` entry) records ``"not_checked"``. Recording that as ``"pass"``
    minted a durable claim that a gate had been satisfied where none exists, and
    it was byte-identical to a genuine clean-gate override — the exact
    indistinguishability this record was built to remove.

    A step that completes normally writes **no** record at all, so the presence of
    an entry is itself the signal.

    Retention: the newest ``MAX_VALIDATION_OVERRIDES`` are kept. An eviction is
    NOT silent — it increments ``validation_overrides_dropped``, so a reader can
    always tell a truncated log from a complete one.
    """
    if ask_issues:
        gate_result = "fail"
    elif checked:
        gate_result = "pass"
    else:
        gate_result = "not_checked"

    record = {
        "step": step,
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "waived": bool(ask_issues),
        "gate_result": gate_result,
        "overridden_issues": [dict(i) for i in ask_issues],
        "inform_count": len(inform_issues),
    }

    log = list(config.get(VALIDATION_OVERRIDES_KEY) or [])
    log.append(record)
    overflow = len(log) - MAX_VALIDATION_OVERRIDES
    if overflow > 0:
        log = log[overflow:]
        previously_dropped = config.get(VALIDATION_OVERRIDES_DROPPED_KEY) or 0
        config[VALIDATION_OVERRIDES_DROPPED_KEY] = int(previously_dropped) + overflow
    config[VALIDATION_OVERRIDES_KEY] = log
    # Returned as well as written. A prior review suggested dropping this as
    # unused surface; external code review objected that removing a return is a
    # compatibility change with no defect behind it, and this is a BUG iterate —
    # so it stays as shipped.
    return record

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


def run_phase_gate(
    project_root: Path, step: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run the phase's own validation plus the opt-in Phase-Quality critical gate.

    Returns ``(ask_issues, inform_issues)``. Read-only: touches no config and
    holds no lock, so the caller runs it OUTSIDE ``run_config_lock`` exactly as
    the inline version did (audit WP2/F11).

    ``validate_phase`` is imported lazily INSIDE this function on purpose:
    ``test_orchestrator.py`` patches ``phase_validators.validate_phase`` — the
    module attribute — which a module-level ``from ... import`` would have
    already bound past. Do not hoist it.

    A validator that RAISES must not wedge the run. Before this change a broken
    validator was escapable with ``--force``, precisely because force skipped it;
    now that force runs the gate too, an unhandled exception would leave no way
    to complete the phase at all. So a crash is caught and returned as an
    ask-level issue: the unforced path still pauses fail-closed with a readable
    reason instead of a traceback, and the forced path still completes — with the
    crash recorded as part of what was overridden.
    """
    try:
        from phase_validators import validate_phase  # noqa: WPS433 — see docstring

        _valid, issues = validate_phase(step, project_root)
        ask_issues = [i for i in issues if i.get("severity") == "ask"]
        inform_issues = [i for i in issues if i.get("severity") == "inform"]

        # Phase-Quality critical-gate (plan § 4.4) — opt-in via
        # SHIPWRIGHT_ENFORCE_CRITICAL_GATES=1, default OFF. Pulls the most recent
        # per-phase finding JSON written by the Stop hook and promotes any
        # W5/W6/W7 FAIL into an ask-level issue. Semantics unchanged by the move;
        # the only difference is that it is no longer skipped under --force.
        if _enforce_critical_gates_enabled():
            finding = _read_latest_phase_quality_finding(project_root, step)
            if finding:
                ask_issues.extend(_collect_critical_gate_issues(finding))

        return ask_issues, inform_issues
    except Exception as exc:  # noqa: BLE001 — a broken gate must not wedge the run
        return (
            [{
                "severity": "ask",
                "message": (
                    f"{GATE_ERROR_PREFIX} validating '{step}' raised "
                    f"{type(exc).__name__}: {exc}"
                ),
            }],
            [],
        )


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
    """Append inform-level validation notes (non-blocking) to the config in place.

    Moved verbatim from ``step_planning``. It now also runs on the forced path,
    which previously computed no issues at all and so silently dropped them.
    """
    if inform_issues:
        notes = config.get("validation_notes", [])
        notes.extend({"step": step, **i} for i in inform_issues)
        config["validation_notes"] = notes


def record_validation_override(
    config: dict[str, Any],
    step: str,
    *,
    reason: str,
    ask_issues: list[dict[str, Any]],
    inform_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    """Append one durable "this phase was completed under override" record, in place.

    ``waived`` is the load-bearing field. ``True`` means the gate FOUND ask-level
    issues and a person decided to go ahead anyway; ``overridden_issues`` carries
    what those were, verbatim. A forced completion over a CLEAN gate records
    ``waived: False`` / ``gate_result: "pass"`` — force was used but nothing was
    actually waived, which is a different fact and worth keeping separate.

    A step that completes normally writes **no** record at all, so the presence of
    an entry is itself the signal.

    Retention: the newest ``MAX_VALIDATION_OVERRIDES`` are kept. An eviction is
    NOT silent — it increments ``validation_overrides_dropped``, so a reader can
    always tell a truncated log from a complete one.
    """
    record = {
        "step": step,
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "waived": bool(ask_issues),
        "gate_result": "fail" if ask_issues else "pass",
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
    return record

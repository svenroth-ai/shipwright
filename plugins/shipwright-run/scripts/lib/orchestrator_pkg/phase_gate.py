"""The phase-gate SEAM of the driven (v2) apply path.

Campaign brief-driven-run-a-real-gates, unit A4 (BRIEF D4 step 2). ``single-session-apply``
used to check only the result shape, claimed artifacts and ``freeze_splits``; no phase
validator ran in a driven run. This module is the one place the apply path asks the phase
validators, and it owns the policy around their answer:

    evaluate_gate      run the gate for ONE phase task (injectable; v1's run_phase_gate by default)
    check_override     the --override-reason preconditions (reason, ok result, a human exists)
    override_hook      the lifecycle hook writing the override record WITH the completion
    rejection          the non-mutating answer when the gate fails, plus the retry position
    is_retryable       whether re-running the phase could fix the findings at all
    gate_summary       the ``gate`` block of a successful apply
    failure_error      the issue summary a gate-terminal mark_phase_failed records

Enforcement is OFF by default (``ENFORCE_PHASE_GATE_DEFAULT``): with it off and no override,
apply never calls the gate and its behaviour is unchanged. A5 migrates the stub-artifact tests
and flips the default. The switch is a function parameter only — no run-config key and no
environment variable can turn the gate off.

Mutations stay in ``phase_task_lifecycle``: nothing here writes run_config or loop state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_LOCAL_LIB = str(Path(__file__).resolve().parents[1])
if _LOCAL_LIB not in sys.path:
    sys.path.insert(0, _LOCAL_LIB)

from single_session.loop_state import (  # noqa: E402
    MAX_GATE_RETRIES,
    gate_retries_exhausted,
    load_loop_state,
)

from .validation_record import (  # noqa: E402
    GATE_ERROR_PREFIX,
    normalise_override_reason,
    record_validation_override,
    run_phase_gate,
)

# A5 flips this to True once every apply test runs on real minimal artifacts.
ENFORCE_PHASE_GATE_DEFAULT = False

# What a gate rejection does once MAX_GATE_RETRIES is exhausted, per run autonomy.
# ``unattended`` (campaign U) behaves at least as autonomous. An unknown value takes the
# non-destructive terminal: a typo must not authorise mark_phase_failed.
TERMINAL_BY_AUTONOMY = {"guided": "ask_human", "autonomous": "failed", "unattended": "failed"}

# Autonomy levels under which no human can be asked, so an override (ASK FIRST in the
# constitution) cannot be a human decision and is refused.
_NO_HUMAN_AUTONOMY = frozenset({"unattended"})

_MAX_ERROR_CHARS = 2000

GateFn = Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]], bool]]


def autonomy_of(config: dict[str, Any]) -> str:
    return str(config.get("autonomy") or "guided")


def evaluate_gate(
    project_root: Path, task: dict[str, Any], config: dict[str, Any], *,
    gate: Optional[GateFn] = None,
) -> dict[str, Any]:
    """Run the gate for ``task``; return ``{ask, inform, checked}``.

    The split is the task's own; the run id is ``config.get("runId")`` forwarded
    unchanged: None when the config has none (the canon bridge then falls back to the
    environment), never a coerced ``""``. An explicitly blank ``runId`` in the config is
    forwarded as-is, so the bridge raises its ask-level finding instead of validating
    against whatever run the environment names. A
    ``kind: canon_degraded`` note is promoted to ask: on this path a canon run that did
    not fully happen must not read as a pass (so a v2 override over it records ``fail``;
    only v1 records ``degraded``). An injected gate that raises becomes one ask-level
    ``[gate-error]`` issue, as ``run_phase_gate`` does for its own.
    """
    phase = task["phase"]
    try:
        ask, inform, checked = (gate or run_phase_gate)(
            project_root, phase, split_id=task.get("splitId"), run_id=config.get("runId"),
        )
    except Exception as exc:  # noqa: BLE001 — a broken gate must not crash apply
        ask, inform, checked = [{
            "severity": "ask",
            "message": f"{GATE_ERROR_PREFIX} the phase gate for '{phase}' raised "
                       f"{type(exc).__name__}: {exc}",
        }], [], True
    degraded = [{**i, "severity": "ask"} for i in inform if i.get("kind") == "canon_degraded"]
    return {
        "ask": [*ask, *degraded],
        "inform": [i for i in inform if i.get("kind") != "canon_degraded"],
        "checked": bool(checked),
    }


def check_override(
    config: dict[str, Any], result: dict[str, Any], override_reason: str,
) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Return ``(reason, None)`` when the override may proceed, else ``(None, rejection)``.

    Refused, before anything runs or is written: a blank reason; an ``ok: false`` result
    (an override completes a phase, a failed phase has nothing to complete); and a run whose
    autonomy has no human to make the decision.
    """
    try:
        reason = normalise_override_reason(override_reason)
    except ValueError:
        return None, {"ok": False, "reason": "override_reason_required",
                      "error": 'single-session-apply --override-reason "<why>" needs a '
                               "non-blank reason: afterwards 'passed its checks' and 'was "
                               "waved through' must still be tellable apart (FR-01.01)."}
    if not result.get("ok"):
        return None, {"ok": False, "reason": "override_requires_ok_result",
                      "error": "--override-reason completes a phase over its gate; "
                               "an ok:false result has nothing to complete."}
    if autonomy_of(config) in _NO_HUMAN_AUTONOMY:
        return None, {"ok": False, "reason": "override_requires_human",
                      "error": f"autonomy {autonomy_of(config)!r} has no human to decide "
                               "an override (constitution ASK FIRST)."}
    return reason, None


def override_hook(
    *, reason: str, verdict: dict[str, Any], autonomy: str,
) -> tuple[Callable[[dict[str, Any], dict[str, Any]], None], dict[str, Any]]:
    """The ``complete_phase_task(on_complete=...)`` hook + the dict it fills with the record."""
    written: dict[str, Any] = {}

    def _hook(config: dict[str, Any], task: dict[str, Any]) -> None:
        written.update(record_validation_override(
            config, task["phase"], reason=reason,
            ask_issues=verdict["ask"], inform_issues=verdict["inform"],
            checked=verdict["checked"],
            via={"phase_task_id": task.get("phaseTaskId"), "split_id": task.get("splitId"),
                 "autonomy": autonomy, "entrypoint": "single-session-apply"},
        ))

    return _hook, written


def retry_position(project_root: Path, config: dict[str, Any]) -> Optional[int]:
    """The current task's dispatch count from ``run_loop_state.json``, or None if unknown.

    Unknown = no loop state, one from another run, or an unreadable/malformed one (a
    direct library apply without ``single-session-next``). ``single-session-next`` always
    writes a matching state, so a driven run never stays unknown.
    """
    try:
        state = load_loop_state(project_root)
    except (OSError, ValueError):  # JSONDecodeError is a ValueError
        return None
    if not isinstance(state, dict) or state.get("runId") != config.get("runId"):
        return None
    try:
        return int(state.get("attempt", 0))
    except (TypeError, ValueError):
        return None


def is_retryable(verdict: dict[str, Any]) -> bool:
    """False when re-running the phase cannot fix a finding: a degraded canon run (the
    environment lacks the verifiers or a run id) or a crashed gate are tool faults, not
    artifact faults, so retries would only burn phase-runner dispatches."""
    return not any(
        i.get("kind") == "canon_degraded"
        or str(i.get("message", "")).startswith(GATE_ERROR_PREFIX)
        for i in verdict["ask"]
    )


def rejection(
    project_root: Path, config: dict[str, Any], verdict: dict[str, Any],
) -> dict[str, Any]:
    """The answer to a failed gate. Non-mutating; the caller executes a ``failed`` terminal.

    ``terminal`` is None while a retry is due, else ``ask_human`` / ``failed`` per autonomy:
    once ``attempt`` exceeds ``MAX_GATE_RETRIES``, or at once for a non-retryable finding.
    ``attempt`` None = no matching loop state (see ``retry_position``): no cap applies, a
    retry is reported as due.
    """
    attempt = retry_position(project_root, config)
    retryable = is_retryable(verdict)
    exhausted = attempt is not None and gate_retries_exhausted(attempt)
    final = exhausted or not retryable
    return {
        "ok": False,
        "reason": "phase_gate_failed",
        "issues": verdict["ask"],
        "inform": verdict["inform"],
        "checked": verdict["checked"],
        "attempt": attempt,
        "max_gate_retries": MAX_GATE_RETRIES,
        "retries_exhausted": exhausted,
        "retryable": retryable,
        "terminal": TERMINAL_BY_AUTONOMY.get(autonomy_of(config), "ask_human") if final else None,
    }


def gate_summary(verdict: dict[str, Any]) -> dict[str, Any]:
    """The ``gate`` block of a successful apply: what ran and what it found."""
    if verdict["ask"]:
        result = "fail"  # only reachable under an override
    else:
        result = "pass" if verdict["checked"] else "not_checked"
    return {"result": result, "checked": verdict["checked"], "issues": verdict["ask"],
            "inform": verdict["inform"]}


def failure_error(verdict: dict[str, Any], attempt: Optional[int]) -> str:
    """The ``errors[]`` line a gate-terminal ``mark_phase_failed`` records (capped)."""
    issues = [str(i.get("message", "")) for i in verdict["ask"]]
    text = (f"phase_gate_failed after {attempt} dispatch(es): {len(issues)} issue(s): "
            + json.dumps(issues, ensure_ascii=False))
    return text if len(text) <= _MAX_ERROR_CHARS else text[: _MAX_ERROR_CHARS - 3] + "..."

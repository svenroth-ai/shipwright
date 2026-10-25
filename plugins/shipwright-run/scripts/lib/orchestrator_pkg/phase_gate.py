"""The phase-gate SEAM of the driven (v2) apply path.

Campaign brief-driven-run-a-real-gates, unit A4 (BRIEF D4 step 2). ``single-session-apply``
used to check only the result shape, claimed artifacts and ``freeze_splits``; no phase
validator ran in a driven run. This module is the one place the apply path asks the phase
validators, and it owns the policy around their answer:

    evaluate_gate      run the gate for ONE phase task (injectable; v1's run_phase_gate by default)
    check_override     the --override-reason preconditions (reason, ok result, a human exists)
    override_hook      the lifecycle hook writing the override record WITH the completion
    retry_state        the loop state when it describes the gated task (else unknown: terminal)
    rejection          the answer when the gate fails, plus the retry position
    is_retryable       whether re-running the phase could fix the findings at all
    gate_summary       the ``gate`` block of a successful apply
    gate_record        the durable ``phase_tasks[].gate`` block written with the completion
    failure_error      the issue summary a gate-terminal mark_phase_failed records

Enforcement is ON by default (``ENFORCE_PHASE_GATE_DEFAULT``, flipped by A5 once every apply
test ran on real minimal artifacts — ``shared/testkit/minimal_valid_project.py``). Off (a test
passing ``enforce_gate=False``) and no override, apply never calls the gate. The switch is a
function parameter only — no run-config key and no environment variable can turn the gate off.

Nothing here writes: run_config mutations stay in ``phase_task_lifecycle`` (the apply path
hands ``gate_record`` / the override record to ``complete_phase_task(on_complete=...)``),
and the apply path counts each rejection in loop state (``gateRejections``).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_LOCAL_LIB = str(Path(__file__).resolve().parents[1])
if _LOCAL_LIB not in sys.path:
    sys.path.insert(0, _LOCAL_LIB)

from orchestrator_pkg.gate_run_id import canon_run_id  # noqa: E402
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

# On since A5: every driven apply runs the phase gate (tests opt out per call).
ENFORCE_PHASE_GATE_DEFAULT = True

# What a gate rejection does once MAX_GATE_RETRIES is exhausted, per run autonomy.
# ``unattended`` (campaign U) behaves at least as autonomous. An unknown value takes the
# non-destructive terminal: a typo must not authorise mark_phase_failed.
TERMINAL_BY_AUTONOMY = {"guided": "ask_human", "autonomous": "failed", "unattended": "failed"}

# The ONLY autonomy levels with a human who can decide an override (ASK FIRST in the
# constitution). An allowlist: ``unattended``, a typo, a case variant or an absent value
# is refused, so no unrecognised spelling can authorise waving a phase through. This stops
# a cooperative caller only; phase-runner.md forbids a runner overriding at all.
_HUMAN_AUTONOMY = frozenset({"guided", "autonomous"})

# Findings a re-dispatch cannot fix (see ``is_retryable``).
_NON_RETRYABLE_KINDS = frozenset({"canon_degraded", "critical_gate", "archived_split"})

_MAX_ERROR_CHARS = 2000

GateFn = Callable[..., tuple[list[dict[str, Any]], list[dict[str, Any]], bool]]


def autonomy_of(config: dict[str, Any]) -> str:
    """The run's autonomy, normalised (stripped, lower-case); absent reads as guided."""
    raw = config.get("autonomy")
    return str(raw).strip().lower() if raw is not None else "guided"


def _human_can_override(config: dict[str, Any]) -> bool:
    raw = config.get("autonomy")
    return isinstance(raw, str) and raw.strip().lower() in _HUMAN_AUTONOMY


def _no_human(config: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "reason": "override_requires_human",
            "error": f"autonomy {config.get('autonomy')!r} has no human to decide an "
                     "override (constitution ASK FIRST; allowed: guided, autonomous)."}


class OverrideRefused(RuntimeError):
    """Raised by the hook when the LOCKED config no longer allows a human override."""


def evaluate_gate(
    project_root: Path, task: dict[str, Any], config: dict[str, Any], *,
    gate: Optional[GateFn] = None,
) -> dict[str, Any]:
    """Run the gate for ``task``; return ``{ask, inform, checked, run_id}``.

    The split is the task's own; the run id is ``gate_run_id.canon_run_id``: the config's
    ``runId``, or the id the phase skill recorded in ``phase_history`` since this task was
    claimed (skills mint their own). An absent ``runId`` stays None (the canon bridge then
    falls back to the environment), never a coerced ``""``; an explicitly blank one is
    forwarded as-is, so the bridge raises its ask-level finding instead of validating
    against whatever run the environment names. A
    ``kind: canon_degraded`` note is promoted to ask: on this path a canon run that did
    not fully happen must not read as a pass (so a v2 override over it records ``fail``;
    only v1 records ``degraded``). An injected gate that raises becomes one ask-level
    ``[gate-error]`` issue, as ``run_phase_gate`` does for its own; so does a
    ``canon_run_id`` that raises (the record then names the config's ``runId``).

    The promotion deliberately REVERSES ``phase_validators_canon._degraded``'s "inform,
    not ask" on this path only: the gate exists to fail closed. That is why A5 proved
    ``shared/scripts/tools/verifiers`` resolves in every layout the plugin ships in
    (``tests/test_phase_gate_cache_layouts.py``) before flipping enforcement on.
    """
    phase = task["phase"]
    run_id = config.get("runId")  # if picking the canon id itself raises
    try:
        run_id = canon_run_id(project_root, task, config)
        ask, inform, checked = (gate or run_phase_gate)(
            project_root, phase, split_id=task.get("splitId"), run_id=run_id,
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
        "run_id": run_id,
    }


def check_override(
    config: dict[str, Any], result: dict[str, Any], override_reason: str,
) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Return ``(reason, None)`` when the override may proceed, else ``(None, rejection)``.

    Refused, before anything runs or is written: a blank reason; an ``ok: false`` result
    (an override completes a phase, a failed phase has nothing to complete); and a run whose
    autonomy is not on the ``_HUMAN_AUTONOMY`` allowlist. The lifecycle hook re-checks the
    autonomy on the LOCKED config, so a config edited in between cannot slip through.
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
    if not _human_can_override(config):
        return None, _no_human(config)
    return reason, None


def override_hook(
    *, reason: str, verdict: dict[str, Any],
) -> tuple[Callable[[dict[str, Any], dict[str, Any]], None], dict[str, Any]]:
    """The ``complete_phase_task(on_complete=...)`` hook + the dict it fills with the record.

    The autonomy is read from the config the lifecycle passes in (the one read under the
    lock) and recorded raw; a value off the allowlist raises, so nothing is written."""
    written: dict[str, Any] = {}

    def _hook(config: dict[str, Any], task: dict[str, Any]) -> None:
        if not _human_can_override(config):
            raise OverrideRefused(_no_human(config)["error"])
        written.update(record_validation_override(
            config, task["phase"], reason=reason,
            ask_issues=verdict["ask"], inform_issues=verdict["inform"],
            checked=verdict["checked"],
            via={"phase_task_id": task.get("phaseTaskId"), "split_id": task.get("splitId"),
                 "autonomy": config.get("autonomy"), "entrypoint": "single-session-apply"},
        ))

    return _hook, written


def retry_state(
    project_root: Path, config: dict[str, Any], phase_task_id: Optional[str],
) -> Optional[dict[str, Any]]:
    """The loop state when it describes THIS task of THIS run; else None (unknown).

    Unknown = no loop state, one from another run, one pointing at a different task, or an
    unreadable/malformed one. Unknown cannot be counted, so ``rejection`` treats it as
    terminal (A5 review): an uncounted rejection must never be retryable forever.
    ``single-session-next`` always writes a matching state, so a driven run that goes
    through it is counted and gets its retries.
    """
    state: Any = None  # bound up front: the loop below always returns or breaks, but say so
    for attempt in (1, 2):  # one re-read: a concurrent os.replace can fail a read on Windows
        try:
            state = load_loop_state(project_root)
            break
        except (OSError, ValueError):  # JSONDecodeError is a ValueError
            if attempt == 2:
                return None
    if (not isinstance(state, dict) or state.get("runId") != config.get("runId")
            or state.get("currentPhaseTaskId") != phase_task_id):
        return None
    try:
        int(state.get("attempt", 0))
        int(state.get("gateRejections", 0))
    except (TypeError, ValueError):
        return None
    return state


def is_retryable(verdict: dict[str, Any]) -> bool:
    """False when re-running the phase cannot fix a finding: a degraded canon run (the
    environment lacks the verifiers or a run id) or a crashed gate are tool faults, not
    artifact faults, so retries would only burn phase-runner dispatches. A Phase-Quality
    critical-gate finding (``kind: critical_gate``) comes from the latest Stop-hook audit
    file, which nothing guarantees is rewritten per dispatch, so a retry may re-read the
    same stale FAIL: it is not retryable either. Nor is a finding on a build split the
    build skill already archived (``kind: archived_split``): a re-dispatched build works on
    the next split."""
    return not any(
        i.get("kind") in _NON_RETRYABLE_KINDS
        or str(i.get("message", "")).startswith(GATE_ERROR_PREFIX)
        for i in verdict["ask"]
    )


def rejection(
    config: dict[str, Any], verdict: dict[str, Any], state: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """The answer to a failed gate. Pure: the caller counts it and runs a ``failed`` terminal.

    ``state`` is ``retry_state``'s answer for the gated task. ``terminal`` is None while a
    retry is due, else ``ask_human`` / ``failed`` per autonomy: once the dispatch
    ``attempt`` or this rejection's number (``gate_rejections``) exceeds
    ``MAX_GATE_RETRIES``, or at once for a non-retryable finding. ``state`` None = unknown
    (``attempt`` and ``gate_rejections`` None): the count cannot be kept, so the terminal is
    taken at once (fail closed) rather than reporting a retry that nothing would cap.
    """
    attempt = int(state.get("attempt", 0)) if state is not None else None
    prior = int(state.get("gateRejections", 0)) if state is not None else None
    retryable = is_retryable(verdict)
    exhausted = state is not None and gate_retries_exhausted(attempt, prior)
    final = state is None or exhausted or not retryable
    return {
        "ok": False,
        "reason": "phase_gate_failed",
        "issues": verdict["ask"],
        "inform": verdict["inform"],
        "checked": verdict["checked"],
        "attempt": attempt,
        "gate_rejections": prior + 1 if prior is not None else None,
        "max_gate_retries": MAX_GATE_RETRIES,
        "retries_exhausted": exhausted,
        "retryable": retryable,
        "terminal": TERMINAL_BY_AUTONOMY.get(autonomy_of(config), "ask_human") if final else None,
        # False = no "go ahead anyway" to offer: check_override would refuse it.
        "override_allowed": _human_can_override(config),
    }


def gate_summary(verdict: dict[str, Any]) -> dict[str, Any]:
    """The ``gate`` block of a successful apply: what ran and what it found."""
    if verdict["ask"]:
        result = "fail"  # only reachable under an override
    else:
        result = "pass" if verdict["checked"] else "not_checked"
    return {"result": result, "checked": verdict["checked"], "issues": verdict["ask"],
            "inform": verdict["inform"]}


def gate_record(task: dict[str, Any], verdict: dict[str, Any], *, overridden: bool,
                at: str) -> dict[str, Any]:
    """The durable ``phase_tasks[].gate`` block a gated completion writes WITH the task:
    what the gate said, for which phase/split, against which run id, when. Inform notes
    are counted, not stored (they stay returned only, A5 decision 5)."""
    return {"result": gate_summary(verdict)["result"], "checked": verdict["checked"],
            "phase": task.get("phase"), "splitId": task.get("splitId"),
            "runId": verdict.get("run_id"), "at": at, "issueCount": len(verdict["ask"]),
            "informCount": len(verdict["inform"]), "overridden": overridden}


def failure_error(verdict: dict[str, Any], attempt: Optional[int]) -> str:
    """The ``errors[]`` line a gate-terminal ``mark_phase_failed`` records (capped)."""
    issues = [str(i.get("message") or i.get("name") or "") for i in verdict["ask"]]
    count = f"after {attempt} dispatch(es)" if attempt is not None else "(dispatch count unknown)"
    text = (f"phase_gate_failed {count}: {len(issues)} issue(s): "
            + json.dumps(issues, ensure_ascii=False))
    return text if len(text) <= _MAX_ERROR_CHARS else text[: _MAX_ERROR_CHARS - 3] + "..."

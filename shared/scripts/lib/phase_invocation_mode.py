"""Invocation-mode authority for the orchestrator-driven phase skills.

**The question this module answers:** *"Was I dispatched by the orchestrator, or did a
human invoke me by hand?"* Every driven phase skill (project / design / plan / build /
test / changelog / deploy) asks it in its First-Actions "Detect Invocation Mode" step,
and the answer decides whether the skill updates pipeline state and how it stamps its
artifacts.

**Why this module exists (iterate-2026-07-14-phase-invocation-mode).** The skills used to
answer it themselves, in prose, from ``shipwright_run_config.json``::

    pipeline  <=>  status == "in_progress" AND current_step == "<my phase>"

``current_step`` / ``completed_steps`` are the **v1** fields. The **v2** pipeline's
authority is ``phase_tasks[]``, and ``phase_task_lifecycle`` — the only writer of phase
state in a driven run — never advances ``current_step``. ``config_factory`` stamps it once
at run creation (``"project"``) and nothing moves it after. So the predicate was FALSE for
every driven phase past the first, and every dispatched phase self-classified as
*standalone*: it skipped its pipeline-state updates and stamped its artifacts
``mode: standalone`` — which ``phase_validators._validate_test`` then *rejects*, demanding
a re-run "within the pipeline" that would misclassify identically. A closed loop.

**The fix — key on the dispatch token, not on run state.** The orchestrator hands the
phase-runner a ``phaseTaskId`` (``single-session-next`` -> dispatch descriptor ->
``agents/phase-runner.md``). Possession of a *valid, actionable* token for *your* phase IS
the definition of "I am a driven phase". It is a **per-invocation** fact; ``current_step``
was a per-run one, and could never have answered the question even if it had been
maintained (it cannot represent a fanned-out build with several concurrent split tasks).

**Three outcomes, never two.** ``standalone`` is reserved for *no token supplied*. A token
that fails to resolve is an ``error`` that STOPs the caller — never a silent downgrade to
standalone, because that downgrade is precisely the bug above, and a transient unreadable
config must not be able to reintroduce it through the back door.

**Trust model.** ``phaseTaskId`` is a *correlation id*, not an authorization capability:
the config is a git-tracked file in the operator's own repo. The validity contract below
(exists + phase matches + actionable) removes the dangerous cases — stale, replayed,
terminal, or wrong-phase ids. It is deliberately not a signed nonce.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

CONFIG_NAME = "shipwright_run_config.json"

# An unsubstituted prompt template: `{phaseTaskId}`, `<phaseTaskId>`, `${...}`, `{{...}}`.
_PLACEHOLDER_RE = re.compile(r"^[\$]?[{<]{1,2}[^}>]*[}>]{1,2}$")

# Self-contained copy of ``phase_task_lifecycle.TERMINAL_STATUSES``. This resolver runs in
# EVERY driven phase — including from a shared-only plugin cache where
# ``plugins/shipwright-run/`` may not be on disk at all — so it must NOT hard-import the
# run plugin: that would turn a missing sibling tree into a crash on every phase. Same
# reasoning (and same remedy) as ``shared/scripts/tools/verifiers/integration_coverage.py``
# (ADR-044). The drift test ``test_terminal_statuses_sync`` pins this == the SSoT.
TERMINAL_STATUSES = frozenset({"done", "failed", "skipped"})

# The orchestrator CLAIMS a phase task (awaiting_launch -> in_progress) *before* it
# dispatches the phase-runner, so a genuinely-dispatched task is always in_progress by the
# time the phase skill resolves its mode. Anything else means the token is stale, replayed,
# or hand-copied out of the config.
ACTIONABLE_STATUS = "in_progress"

PIPELINE = "pipeline"
STANDALONE = "standalone"
ERROR = "error"


def read_run_config(project_root: Path) -> Optional[dict[str, Any]]:
    """Parse the v2 run config, or ``None`` when absent / corrupt / v1. Never raises.

    "Corrupt" includes a v2-SHAPED but structurally invalid config — e.g.
    ``{"schemaVersion": 2, "phase_tasks": [null]}`` or ``phase_tasks: {}``. Checking only
    the top-level dict would let a malformed entry reach ``task.get(...)`` and raise
    ``AttributeError`` deep in the resolver, breaking the "never raises" contract exactly
    when it matters most — a token-bearing invocation, which must produce a structured
    ``error``, not a traceback (external code review, GPT).
    """
    config_path = Path(project_root) / CONFIG_NAME
    if not config_path.exists():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(config, dict) or config.get("schemaVersion") != 2:
        return None
    tasks = config.get("phase_tasks")
    if tasks is not None and (
        not isinstance(tasks, list) or any(not isinstance(t, dict) for t in tasks)
    ):
        return None
    return config


def _malformed_token_reason(token: str) -> Optional[tuple[str, str]]:
    """``(reason, message)`` if ``token`` is a supplied-but-unusable token, else ``None``.

    **Only an ABSENT token means standalone.** A token that was supplied but is garbage is
    an ``error``, never a silent downgrade. Two shapes are easy to pass by accident:

    * empty / blank — ``--phase-task-id ""`` (external code review, GPT);
    * an UNSUBSTITUTED prompt placeholder — ``{phaseTaskId}``, ``<phaseTaskId>``. The skills
      carry the flag inline in a template, so a caller can pass the literal (Stage-3 doubt
      review).

    Both could plausibly be mapped to ``standalone`` instead — and for a *hand* invocation
    that would even be the nicer outcome. They are errors anyway, because the SAME shapes
    arise when a driven master fails to substitute the real token, and there standalone is
    the silent catastrophe this whole module exists to prevent. Loud-and-recoverable beats
    silent-and-wrong: the message names the fix (drop the flag), so a hand-invoker recovers
    in one step, while a broken dispatch can no longer masquerade as a standalone run.
    """
    if not token.strip():
        return (
            "invalid_phase_task_id",
            "--phase-task-id was supplied but is empty. If you were NOT dispatched by the "
            "orchestrator, OMIT the flag entirely (that is what selects standalone mode); "
            "an empty token is a briefing bug, not a standalone run.",
        )
    if _PLACEHOLDER_RE.match(token.strip()):
        return (
            "unsubstituted_phase_task_id_placeholder",
            f"--phase-task-id was passed the literal template placeholder {token!r} instead "
            "of a real phaseTaskId. If you were NOT dispatched by the orchestrator, OMIT the "
            "flag entirely to run standalone. If you WERE dispatched, the master failed to "
            "substitute the token — surface that rather than proceeding.",
        )
    return None


def live_run_snapshot(project_root: Path) -> tuple[bool, list[str]]:
    """``(pipeline_active, active_phases)`` — is a driven run live right now?

    "Live" is defined against the lifecycle state machine, not an ad-hoc status list: the
    run is ``in_progress`` and at least one ``phase_tasks[]`` entry is non-terminal per
    :data:`TERMINAL_STATUSES`. Reads ONLY v2 fields — never ``current_step`` /
    ``completed_steps``, whose staleness is the whole reason this module exists.

    ``active_phases`` is deduplicated (a fanned-out build has several concurrent split
    tasks on the SAME phase) and sorted, so the warning message is stable.
    """
    config = read_run_config(project_root)
    if config is None or config.get("status") != "in_progress":
        return False, []
    active = {
        str(task.get("phase"))
        for task in (config.get("phase_tasks") or [])
        if task.get("status") not in TERMINAL_STATUSES and task.get("phase")
    }
    return bool(active), sorted(active)


def _standalone_payload(project_root: Path) -> dict[str, Any]:
    """No dispatch token ⇒ a hand-invoked, out-of-band run. The ONLY standalone path."""
    pipeline_active, active_phases = live_run_snapshot(project_root)
    if pipeline_active:
        hint = (
            "A driven pipeline run is LIVE at phase(s): "
            f"{', '.join(active_phases)}. You were NOT dispatched by the orchestrator "
            "(no phaseTaskId), so this is an out-of-band invocation that may collide "
            "with it. WARN the user and ASK before continuing."
        )
    else:
        hint = (
            "No active shipwright-run pipeline detected. Proceed with the skill's "
            "normal Step 1 — there is no pipeline metadata to load."
        )
    return {
        "mode": STANDALONE,
        "reason": "no_phase_task_id",
        "phaseTaskId": None,
        "pipeline_active": pipeline_active,
        "active_phases": active_phases,
        # Pre-computed so the skill does a binary check instead of reasoning about
        # set-membership in prose (external plan review, Gemini #1).
        "requires_out_of_sequence_warning": pipeline_active,
        "next_action_hint": hint,
    }


def _error_payload(reason: str, phase_task_id: str, message: str) -> dict[str, Any]:
    """A token WAS supplied but does not resolve to a valid, actionable task ⇒ STOP.

    Continuing as ``standalone`` here would let a genuinely driven phase skip its
    pipeline-state updates and stamp its artifacts ``mode: standalone`` — the exact
    failure this iterate removes (external plan review, GPT #2, severity high).
    """
    return {
        "mode": ERROR,
        "reason": reason,
        "phaseTaskId": phase_task_id,
        "message": message,
        "next_action_hint": (
            "STOP. You were dispatched with a phaseTaskId but it does not resolve to a "
            "valid, actionable phase task. Do NOT continue as standalone. Surface this "
            "to the orchestrator (an ok:false phase result), or run `orchestrator.py "
            "recover-phase-task` to release the task before re-launching."
        ),
    }


def resolve_invocation_mode(
    project_root: Path,
    phase_task_id: Optional[str],
    phase: Optional[str] = None,
) -> tuple[dict[str, Any], Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Resolve the invocation mode. Never raises.

    Returns ``(payload, task, config)``. ``task`` and ``config`` are non-``None`` only for
    a ``pipeline`` verdict, so a caller that needs to enrich the payload (e.g. the Step-0
    context tool, which appends prerequisites + artifact suggestions) does not re-read the
    config. For ``standalone`` and ``error`` the payload is final.

    ``phase`` is the caller's OWN phase (e.g. ``"build"``). When supplied, a token that
    points at a *different* phase is rejected: a stale or hand-copied id must not grant
    pipeline authority over someone else's task.
    """
    # ONLY an absent token means standalone.
    if phase_task_id is None:
        return _standalone_payload(project_root), None, None

    malformed = _malformed_token_reason(phase_task_id)
    if malformed is not None:
        reason, message = malformed
        return _error_payload(reason, phase_task_id, message), None, None

    phase_task_id = phase_task_id.strip()

    root = Path(project_root)
    if not (root / CONFIG_NAME).exists():
        return _error_payload(
            "no_run_config", phase_task_id,
            f"dispatched with phaseTaskId {phase_task_id} but no {CONFIG_NAME} exists "
            f"at {root}",
        ), None, None

    config = read_run_config(root)
    if config is None:
        return _error_payload(
            "run_config_unreadable", phase_task_id,
            f"{CONFIG_NAME} is unreadable, corrupt, or not schemaVersion 2 — cannot "
            f"resolve phaseTaskId {phase_task_id}",
        ), None, None

    tasks = config.get("phase_tasks") or []
    task = next((t for t in tasks if t.get("phaseTaskId") == phase_task_id), None)
    if task is None:
        return _error_payload(
            "phase_task_id_not_found", phase_task_id,
            f"phaseTaskId {phase_task_id} is not in phase_tasks[]",
        ), None, None

    if phase and task.get("phase") != phase:
        return _error_payload(
            "wrong_phase_for_phase_task", phase_task_id,
            f"phaseTaskId {phase_task_id} belongs to phase {task.get('phase')!r}, but "
            f"this is the {phase!r} skill. Re-launch with the correct slash command.",
        ), None, None

    status = task.get("status")
    if status != ACTIONABLE_STATUS:
        # Name the remedy, don't just refuse. `awaiting_launch` is the recoverable case: it
        # means the task was never CLAIMED, which happens if a master briefs a phase-runner
        # straight from the read-only resume descriptor (`single_session_recovery`) instead
        # of re-calling `single-session-next`. Refusing is right — an unclaimed task grants
        # no pipeline authority — but a bare refusal would fail the whole run, so say how to
        # fix it (Stage-3 doubt review).
        if status == "awaiting_launch":
            remedy = (
                "The task exists but was never CLAIMED. Do not dispatch from a read-only "
                "resume descriptor: re-run `orchestrator.py single-session-next`, which "
                "claims the task and hands you a live token."
            )
        else:
            remedy = (
                "A terminal task means this token is stale or replayed. Use "
                "`orchestrator.py recover-phase-task` to release it before re-launching."
            )
        return _error_payload(
            "phase_task_not_actionable", phase_task_id,
            f"phaseTaskId {phase_task_id} has status {status!r}, expected "
            f"{ACTIONABLE_STATUS!r} (the orchestrator claims a task before dispatching it). "
            f"{remedy}",
        ), None, None

    payload: dict[str, Any] = {
        "mode": PIPELINE,
        "runId": config.get("runId"),
        "phaseTaskId": task.get("phaseTaskId"),
        "phase": task.get("phase"),
        "splitId": task.get("splitId"),
        "version": task.get("version"),
        "slashCommand": task.get("slashCommand"),
        "runConditions": config.get("runConditions") or {},
        "splits_frozen": config.get("splits_frozen") or [],
    }
    return payload, task, config

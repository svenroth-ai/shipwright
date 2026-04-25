"""Pure-function pipeline state machine for the multi-session run orchestrator.

Single source of truth for "given a completed phase task, what is the next one".
Returns descriptive specs (not full phase_tasks[] entries) — the caller
(orchestrator.plan_next_phase) generates IDs and writes to disk.

Contract:
    - No I/O. No side-effects. Pure function only.
    - Input/output use TypedDicts for strict typing.
    - phase and splitId are ALWAYS stored separately, never as a combined
      string like "plan/01-core". The caller is responsible for any display
      formatting.

Run-completion invariant (Plan v3 §State Machine):
    The state machine returns None when the deploy task is done. The caller
    must additionally verify ALL phase_tasks are terminal before flipping
    run.status = complete. The state machine itself does not enforce that —
    it only describes transitions.
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict


# ---- Types ----

Phase = Literal[
    "project", "design", "plan", "build", "test", "security", "changelog", "deploy",
]

PhaseTaskStatus = Literal[
    "backlog", "awaiting_launch", "in_progress", "done", "failed", "skipped",
]

TerminalStatus = Literal["done", "failed", "skipped"]


class RunConditions(TypedDict):
    """Frozen at run creation. Mid-run env changes do not affect this."""
    securityEnabled: bool
    splitMode: Optional[Literal["none", "per_split"]]
    aikidoClientIdPresent: bool


class CompletedPhaseTask(TypedDict):
    """Minimal subset of a phase_tasks[] entry needed to compute the next step."""
    phaseTaskId: str
    phase: Phase
    splitId: Optional[str]
    status: TerminalStatus  # only terminal states are valid as input


class NextPhaseSpec(TypedDict):
    """Descriptive next-phase spec. Caller fills in phaseTaskId, sessionUuid, etc."""
    phase: Phase
    splitId: Optional[str]
    prerequisites: list[str]  # phaseTaskIds upstream (typically just the predecessor)
    slashCommand: str
    titleSuffix: str  # for display, e.g. "build / 02-ui-shell" or "test"


# ---- Public API ----


def initial_phase_spec() -> NextPhaseSpec:
    """The first phase of any run. Constant — does not depend on run config."""
    return _spec("project", split_id=None, prereqs=[])


def next_phase_task(
    *,
    run_conditions: RunConditions,
    splits_frozen: list[str],
    completed: CompletedPhaseTask,
) -> Optional[NextPhaseSpec]:
    """Return spec for next phase task, or None if the pipeline is terminal.

    Pre-conditions:
        - completed.status must be a terminal status (done / failed / skipped).
        - splits_frozen must reflect post-design state when computing transitions
          out of design/plan/build. Before design is done, callers should not
          ask the state machine for plan/* successors.

    Failure semantics:
        - This function does NOT branch on completed.status == "failed". The
          orchestrator is responsible for halting the pipeline on failure
          (Plan v3 §State Machine "Failure-Branch"). next_phase_task returns
          the structural successor regardless of status; the caller decides
          whether to materialize it.

    Returns None when:
        - Predecessor is deploy (pipeline-terminal), OR
        - splits_frozen is depleted in the build/<split> branch.
    """
    phase = completed["phase"]
    split_id = completed["splitId"]
    prereq = [completed["phaseTaskId"]]

    if phase == "project":
        return _spec("design", split_id=None, prereqs=prereq)

    if phase == "design":
        split_mode = run_conditions["splitMode"]
        if split_mode == "per_split":
            if not splits_frozen:
                # defensive: per_split declared but no splits — coerce to single pass
                return _spec("plan", split_id=None, prereqs=prereq)
            return _spec("plan", split_id=splits_frozen[0], prereqs=prereq)
        # splitMode == "none" or None (not yet frozen — defensive single pass)
        return _spec("plan", split_id=None, prereqs=prereq)

    if phase == "plan":
        return _spec("build", split_id=split_id, prereqs=prereq)

    if phase == "build":
        if split_id is None:
            # split-less build → straight to test
            return _spec("test", split_id=None, prereqs=prereq)
        # per-split build → next plan/<split[i+1]> if remaining, else test
        try:
            i = splits_frozen.index(split_id)
        except ValueError:
            # split_id not in frozen list — corrupted state, treat as terminal split
            return _spec("test", split_id=None, prereqs=prereq)
        if i + 1 < len(splits_frozen):
            return _spec("plan", split_id=splits_frozen[i + 1], prereqs=prereq)
        return _spec("test", split_id=None, prereqs=prereq)

    if phase == "test":
        if run_conditions["securityEnabled"]:
            return _spec("security", split_id=None, prereqs=prereq)
        return _spec("changelog", split_id=None, prereqs=prereq)

    if phase == "security":
        return _spec("changelog", split_id=None, prereqs=prereq)

    if phase == "changelog":
        return _spec("deploy", split_id=None, prereqs=prereq)

    if phase == "deploy":
        return None  # pipeline-terminal — caller checks run-completion invariant

    raise ValueError(f"Unknown phase: {phase!r}")


# ---- Internals ----


_SLASH_COMMAND: dict[Phase, str] = {
    "project": "/shipwright-project",
    "design": "/shipwright-design",
    "plan": "/shipwright-plan",
    "build": "/shipwright-build",
    "test": "/shipwright-test",
    "security": "/shipwright-security",
    "changelog": "/shipwright-changelog",
    "deploy": "/shipwright-deploy",
}


def _spec(phase: Phase, *, split_id: Optional[str], prereqs: list[str]) -> NextPhaseSpec:
    title_suffix = f"{phase} / {split_id}" if split_id else phase
    return {
        "phase": phase,
        "splitId": split_id,
        "prerequisites": list(prereqs),
        "slashCommand": _SLASH_COMMAND[phase],
        "titleSuffix": title_suffix,
    }


def freeze_run_conditions(*, aikido_client_id: Optional[str]) -> RunConditions:
    """Compute the frozen run_conditions block from the current environment.

    Helper called at run creation by orchestrator.create_config. splitMode stays
    None until design completes — the design-stop hook calls freeze-splits which
    sets it. aikidoClientIdPresent mirrors the cause for diagnostic clarity.
    """
    has_aikido = bool((aikido_client_id or "").strip())
    return {
        "securityEnabled": has_aikido,
        "splitMode": None,
        "aikidoClientIdPresent": has_aikido,
    }

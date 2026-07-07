"""Single-session pipeline scaffold (Campaign 2026-07-07, SS1).

SCAFFOLD ONLY — this package lands the *contracts* the single-session pipeline
mode is built on; it runs no phase and drives no loop. SS3 wires the
orchestrator loop, SS4 the phase-runner subagent + artifact persistence.

Two contracts live here:

  * ``result_contract`` — the COMPACT structured result a phase-runner subagent
    returns. It is the exact ``result`` payload handed to
    ``phase_task_lifecycle.complete_phase_task`` — ONE result shape, ONE
    completion path.
  * ``loop_state`` — the orchestrator's own resumable pointer/counter state,
    persisted to ``.shipwright/run_loop_state.json`` (distinct from the
    campaign's ``.shipwright/loop_state.json``). It holds NO authoritative
    phase status and never mutates ``shipwright_run_config.json`` — the
    lifecycle-reuse contract (no parallel completion path).

``LIFECYCLE_COMPLETION_ENTRYPOINTS`` names the ONLY phase-task mutation
entrypoints the SS3 orchestrator may call — every one resolves to a callable in
``phase_task_lifecycle``. It is the machine-checkable statement of "reuse the
lifecycle, add no bespoke completion path" (see
``tests/test_single_session_lifecycle_reuse.py``).
"""
from __future__ import annotations

from .loop_state import (
    LOOP_STATE_REL_PATH,
    LOOP_STATE_SCHEMA_VERSION,
    LOOP_STATUSES,
    advance_pointer,
    init_loop_state,
    load_loop_state,
    loop_state_path,
    record_dispatch,
    save_loop_state,
    set_status,
)
from .result_contract import (
    MAX_SUMMARY_CHARS,
    REQUIRED_RESULT_KEYS,
    VALID_PHASES,
    ResultContractError,
    build_phase_runner_result,
    is_valid_result,
    validate_phase_runner_result,
)

# The single-session orchestrator (SS3) mutates phase-task state ONLY through
# these phase_task_lifecycle entrypoints. No parallel completion path exists in
# this package. Kept as a tuple so the lifecycle-reuse contract test can prove
# each name resolves to a real lifecycle callable (forward drift guard).
LIFECYCLE_COMPLETION_ENTRYPOINTS = (
    "complete_phase_task",
    "mark_phase_failed",
    "recover_phase_task",
    "plan_next_phase",
)

__all__ = [
    # result contract
    "MAX_SUMMARY_CHARS",
    "REQUIRED_RESULT_KEYS",
    "VALID_PHASES",
    "ResultContractError",
    "build_phase_runner_result",
    "is_valid_result",
    "validate_phase_runner_result",
    # loop state
    "LOOP_STATE_REL_PATH",
    "LOOP_STATE_SCHEMA_VERSION",
    "LOOP_STATUSES",
    "advance_pointer",
    "init_loop_state",
    "load_loop_state",
    "loop_state_path",
    "record_dispatch",
    "save_loop_state",
    "set_status",
    # lifecycle reuse
    "LIFECYCLE_COMPLETION_ENTRYPOINTS",
]

"""Orchestrator package — split of the historical monolithic
``orchestrator.py`` (983 LOC) in Campaign B5 (2026-05-26).

The historical ``orchestrator.py`` import surface is preserved by the
sibling shim file ``../orchestrator.py``, which re-exports the same
names from this package. New code should import from ``orchestrator``
(the shim) or directly from the relevant submodule below — both work.

Submodule layout:

    constants         — schema versions, paths, allowlists
    events            — record_event.py wrappers (non-blocking)
    config_io         — load_run_config / save_run_config / is_v2_config
    legacy_migration  — drop compliance/security from legacy pipelines
    config_factory    — build_pipeline + create_config
    compliance_runner — run_compliance_update (subprocess wrapper)
    critical_gates    — Phase-Quality W5/W6/W7 critical-gate helpers
    build_progress    — get_build_progress
    step_planning     — get_next_step + update_step
    router            — F2 phase-lifecycle subcommand dispatcher
    cli               — argparse + main()

Public re-exports below match the names previously exposed by
``orchestrator.py`` so existing callers stay green.
"""
from __future__ import annotations

from .build_progress import get_build_progress
from .compliance_runner import run_compliance_update
from .config_factory import build_pipeline, create_config
from .config_io import (
    is_legacy_multi_session,
    is_single_session,
    is_v2_config,
    load_run_config,
    mode_rejection,
    save_run_config,
)
from .constants import (
    CONFIG_NAME,
    DEFAULT_RUN_MODE,
    PIPELINE_STEPS,
    RUN_MODES,
    SCHEMA_VERSION,
    _COMPLIANCE_SCRIPT,
    _CRITICAL_GATE_CHECK_IDS,
    _LEGACY_PIPELINE_ENTRIES,
)
from .critical_gates import (
    _collect_critical_gate_issues,
    _enforce_critical_gates_enabled,
    _read_latest_phase_quality_finding,
)
from .events import (
    _record_compliance_update_failed,
    _record_pipeline_migration_event,
)
from .step_planning import get_next_step, update_step

__all__ = [
    "CONFIG_NAME",
    "PIPELINE_STEPS",
    "SCHEMA_VERSION",
    "RUN_MODES",
    "DEFAULT_RUN_MODE",
    "_COMPLIANCE_SCRIPT",
    "_CRITICAL_GATE_CHECK_IDS",
    "_LEGACY_PIPELINE_ENTRIES",
    "build_pipeline",
    "create_config",
    "get_build_progress",
    "get_next_step",
    "is_v2_config",
    "load_run_config",
    "is_single_session",
    "is_legacy_multi_session",
    "mode_rejection",
    "run_compliance_update",
    "save_run_config",
    "update_step",
    "_collect_critical_gate_issues",
    "_enforce_critical_gates_enabled",
    "_read_latest_phase_quality_finding",
    "_record_compliance_update_failed",
    "_record_pipeline_migration_event",
]

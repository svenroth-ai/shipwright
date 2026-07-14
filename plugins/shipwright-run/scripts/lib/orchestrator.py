#!/usr/bin/env python3
"""Orchestrator for shipwright-run — thin re-export shim.

Real implementation lives in ``orchestrator_pkg/`` (Campaign B5,
2026-05-26 split of the 983-LOC monolith). The shim preserves
``from orchestrator import X`` AND ``python orchestrator.py CMD``
for historical callers, and holds the test-patched names
(``run_compliance_update``, ``_COMPLIANCE_SCRIPT``, ``_record_*``)
on its module namespace so ``mocker.patch("orchestrator.X")`` works.

CLI:
    uv run orchestrator.py write-config --scope <scope> --profile <profile> --autonomy <level>
    uv run orchestrator.py get-next-step --project-root <path>
    uv run orchestrator.py update-step --project-root <path> --step <step> --status <status>
"""
from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent
_SHARED_SCRIPTS = _LIB.parent.parent.parent.parent / "shared" / "scripts"
for _p in (str(_LIB), str(_SHARED_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from orchestrator_pkg import (  # noqa: E402,F401
    CONFIG_NAME, DEFAULT_RUN_MODE, PIPELINE_STEPS, RUN_MODES, SCHEMA_VERSION,
    _COMPLIANCE_SCRIPT, _CRITICAL_GATE_CHECK_IDS, _LEGACY_PIPELINE_ENTRIES,
    _collect_critical_gate_issues, _enforce_critical_gates_enabled,
    _read_latest_phase_quality_finding,
    _record_compliance_update_failed, _record_pipeline_migration_event,
    build_pipeline, create_config, get_build_progress, get_next_step,
    is_legacy_multi_session, is_single_session, is_v2_config, load_run_config,
    mode_rejection, run_compliance_update,
    save_run_config, update_step,
)
from orchestrator_pkg.cli import main  # noqa: E402
from orchestrator_pkg.router import dispatch_lifecycle as _dispatch_lifecycle  # noqa: E402,F401

if __name__ == "__main__":
    sys.exit(main())

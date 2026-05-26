"""Constants for the orchestrator package.

Split out of the monolithic ``orchestrator.py`` in Campaign B5 (2026-05-26).
"""
from __future__ import annotations

import sys
from pathlib import Path

# --- Path bootstrap --------------------------------------------------------
# orchestrator_pkg lives at:
#   plugins/shipwright-run/scripts/lib/orchestrator_pkg/constants.py
# parents[0] = orchestrator_pkg
# parents[1] = lib
# parents[2] = scripts
# parents[3] = shipwright-run
# parents[4] = plugins
# parents[5] = repo root
_SHARED_SCRIPTS = (
    Path(__file__).resolve().parents[5] / "shared" / "scripts"
)
_LOCAL_LIB = str(Path(__file__).resolve().parents[1])
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
if _LOCAL_LIB not in sys.path:
    sys.path.insert(0, _LOCAL_LIB)

# --- Schema constants ------------------------------------------------------
CONFIG_NAME = "shipwright_run_config.json"

# Multi-session pipeline schema version. F2+ phase-lifecycle subcommands
# (claim-phase-task, complete-phase-task, etc.) hard-fail on anything else.
SCHEMA_VERSION = 2

# Compliance plugin location (sibling plugin)
_THIS_PLUGIN = Path(__file__).resolve().parents[3]
_COMPLIANCE_SCRIPT = (
    _THIS_PLUGIN.parent
    / "shipwright-compliance"
    / "scripts"
    / "tools"
    / "update_compliance.py"
)

PIPELINE_STEPS = ["project", "design", "plan", "build", "test", "changelog", "deploy"]

# Legacy pipeline entries removed by load_run_config migration. Kept for
# documentation: projects migrated off a prior pipeline get those entries
# dropped from `pipeline` (not replayed) but preserved in `completed_steps`
# as a historical marker.
#
#   "compliance" — removed earlier (plan v7 Option Z); compliance is now an
#       auto-background side-effect + on-demand /shipwright-compliance audit.
#   "security" — removed in iterate sec-report-and-orchestrator-decouple
#       (2026); security is now manual via /shipwright-security or scheduled
#       via .github/workflows/security.yml.
_LEGACY_PIPELINE_ENTRIES: frozenset[str] = frozenset({"compliance", "security"})

# Plan § 4.4 / 9.2 — Orchestrator gate Critical-Check allowlist.
# These FAILs block phase-transition only when
# ``SHIPWRIGHT_ENFORCE_CRITICAL_GATES=1`` is set. Default OFF in code.
_CRITICAL_GATE_CHECK_IDS: frozenset[str] = frozenset({"W5", "W6", "W7"})


__all__ = [
    "CONFIG_NAME",
    "SCHEMA_VERSION",
    "PIPELINE_STEPS",
    "_LEGACY_PIPELINE_ENTRIES",
    "_CRITICAL_GATE_CHECK_IDS",
    "_COMPLIANCE_SCRIPT",
    "_SHARED_SCRIPTS",
    "_THIS_PLUGIN",
]

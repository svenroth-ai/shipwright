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

# Pipeline execution mode (Campaign 2026-07-07, SS1 — additive scaffold).
#   single_session — the /shipwright-run master drives every phase via a
#                    phase-runner subagent in ONE conversation (SS3). SS8: the
#                    DEFAULT and sole supported mode.
#   multi_session  — each phase = its own external UUID-bound Claude session
#                    (the pre-SS1 behaviour). DEPRECATED; now only the legacy
#                    read-fallback (LEGACY_FALLBACK_MODE), no longer the default.
# DEFAULT_RUN_MODE is what a FRESH run gets. SS8 (2026-07-08): single_session is
# now the SOLE mode — a fresh /shipwright-run with no explicit --mode selects it.
# LEGACY_FALLBACK_MODE is the SEPARATE fallback for READING a mode-less /
# unrecognized config (config_io.run_mode): kept at multi_session so an existing
# pre-flip run is NOT silently reinterpreted mid-flight — the one user migrates
# EXPLICITLY (set mode: single_session + resume; see
# docs/migrations/multi-session-to-single-session.md).
# Multi-session is DEPRECATED; code-path removal is deferred (triage trg-0e8e7f90).
RUN_MODES = ("multi_session", "single_session")
DEFAULT_RUN_MODE = "single_session"
LEGACY_FALLBACK_MODE = "multi_session"

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
    "RUN_MODES",
    "DEFAULT_RUN_MODE",
    "LEGACY_FALLBACK_MODE",
    "PIPELINE_STEPS",
    "_LEGACY_PIPELINE_ENTRIES",
    "_CRITICAL_GATE_CHECK_IDS",
    "_COMPLIANCE_SCRIPT",
    "_SHARED_SCRIPTS",
    "_THIS_PLUGIN",
]

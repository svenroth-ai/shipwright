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

# Pipeline schema version. F2+ phase-lifecycle subcommands (claim-phase-task,
# complete-phase-task, etc.) hard-fail on anything else.
SCHEMA_VERSION = 2

# Pipeline execution mode. ``single_session`` is the SOLE mode: the
# /shipwright-run master drives every phase via a phase-runner subagent in ONE
# conversation, so the pipeline advances on every surface (CLI, VS Code, desktop).
#
# The former ``multi_session`` mode — each phase its own external UUID-bound
# Claude session, claimed/completed by SessionStart+Stop hooks — was removed
# together with its engine in
# iterate-2026-07-14-remove-multi-session (triage trg-0e8e7f90).
RUN_MODES = ("single_session",)
DEFAULT_RUN_MODE = "single_session"

# Removal tombstone — NOT a selectable mode.
#
# We still RECOGNISE this literal so a config written before the removal fails
# CLOSED with an actionable migration message instead of being silently
# reinterpreted as single_session (which would resume a run under an execution
# model its engine no longer implements). It also stays in the ``--mode``
# argparse choices: dropping it there would make argparse emit a generic
# "invalid choice" error *before* our migration message could ever print.
#
# Recognition is deliberately confined to the EXECUTION path (write-config and
# the single-session subcommands). ``config_io.load_run_config`` stays a pure
# reader that never raises on it, so read-only inspection of a historical run
# (WebUI run history, .shipwright/runs/**) keeps working.
LEGACY_MULTI_SESSION = "multi_session"

MIGRATION_DOC = "docs/migrations/multi-session-to-single-session.md"

_MIGRATION_STEPS = (
    'To migrate: set "mode": "single_session" in shipwright_run_config.json, then '
    "re-invoke /shipwright-run to resume. phase_tasks[] are shared and re-claim is "
    f"idempotent, so no phase work is lost. See {MIGRATION_DOC}."
)

# An explicit `multi_session` choice whose engine no longer exists.
LEGACY_MODE_MESSAGE = (
    "This run config records the REMOVED pipeline mode 'multi_session'. Each phase "
    "used to run as its own external bound Claude session, advanced by SessionStart/"
    "Stop hooks; that engine is gone — single_session is the sole mode.\n"
    + _MIGRATION_STEPS
)

# A config that never declared a mode (pre-SS1) — or declared something unknown.
# It is not being reinterpreted for it; it just has to name the only mode there is.
MODE_REQUIRED_MESSAGE = (
    "This run config does not record 'mode': 'single_session', so it is not a "
    "drivable pipeline run. single_session is the sole mode.\n"
    + _MIGRATION_STEPS
)

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
    "LEGACY_MULTI_SESSION",
    "LEGACY_MODE_MESSAGE",
    "MODE_REQUIRED_MESSAGE",
    "MIGRATION_DOC",
    "PIPELINE_STEPS",
    "_LEGACY_PIPELINE_ENTRIES",
    "_CRITICAL_GATE_CHECK_IDS",
    "_COMPLIANCE_SCRIPT",
    "_SHARED_SCRIPTS",
    "_THIS_PLUGIN",
]

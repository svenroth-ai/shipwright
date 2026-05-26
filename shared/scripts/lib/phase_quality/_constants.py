"""Constants for the Phase-Quality-Audit package.

Single home for plugin→phase mapping, category coverage sets, paths,
and status string constants. Imported by every other ``phase_quality``
submodule + by ``audit_phase_quality_on_stop.py``.

Iterate Campaign B (B3): split out of the 1108-LOC ``phase_quality.py``
monolith. Constants live HERE so producers/consumers cannot drift on
phase-set membership.
"""

from __future__ import annotations

PLUGIN_TO_PHASE: dict[str, str] = {
    "shipwright-project": "project",
    "shipwright-design": "design",
    "shipwright-plan": "plan",
    "shipwright-build": "build",
    "shipwright-test": "test",
    "shipwright-security": "security",
    "shipwright-deploy": "deploy",
    "shipwright-changelog": "changelog",
    "shipwright-compliance": "compliance",
    "shipwright-iterate": "iterate",
    "shipwright-adopt": "adopt",
}

# Phases that take ADR-worthy decisions (C4 applies).
# `adopt` included because /shipwright-adopt seeds ADR-0001 (adoption decision).
C4_PHASES: frozenset[str] = frozenset({"project", "plan", "build", "iterate", "adopt"})

# User-facing phases that prepend a CHANGELOG bullet (C5 applies).
C5_PHASES: frozenset[str] = frozenset({"project", "design", "build", "deploy", "iterate"})

# C5 Keep-a-Changelog category per phase.
C5_CATEGORY: dict[str, str] = {
    "project": "Added",
    "design": "Added",
    "build": "Added",
    "deploy": "Changed",
    "iterate": "Added",
}

# Tier classification — Tier-2 means "heuristic, never enforcement" (plan § 3).
# C1-C5 are all Tier-1.
TIER_2_CHECK_IDS: frozenset[str] = frozenset({
    "W1", "I4", "T2", "Q1", "S3", "S4", "S5", "S7", "S9", "S10", "Cmp1", "D2",
    # Adopt-specific Tier-2 (heuristic, non-blocking):
    #   A4 = ADR-backfill quality, A5 = Layer-3 review presence,
    #   A8 = E2E baseline suite existence.
    "A4", "A5", "A8",
})

CATEGORIES: tuple[str, ...] = (
    "canon", "workflow", "infrastructure", "traceability", "quality", "spec",
)

MAX_REPORT_RUNS = 10
MAX_SESSION_SUMMARY_RUNS = 5
GC_AGE_DAYS = 90

COMPLIANCE_DIR = ".shipwright/compliance"
LEGACY_COMPLIANCE_DIRNAME = "compliance"

FINDING_DIR = f"{COMPLIANCE_DIR}/skill-compliance"
REPORT_PATH = f"{COMPLIANCE_DIR}/skill-compliance-report.md"
SUMMARY_PATH = ".shipwright/agent_docs/skill-compliance-findings.md"
DASHBOARD_PATH = f"{COMPLIANCE_DIR}/skill-compliance-dashboard.md"
LOCK_PATH = ".shipwright/locks/phase-quality.lock"

# Finding status constants.
STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_WARN = "WARN"
STATUS_SKIP = "SKIP"

# Markers used by the audit hook to identify a Shipwright project layout.
CONFIG_MARKERS: tuple[str, ...] = (
    "shipwright_run_config.json",
    "shipwright_project_config.json",
    "shipwright_plan_config.json",
    "shipwright_build_config.json",
    "shipwright_events.jsonl",
)


__all__ = [
    "C4_PHASES",
    "C5_CATEGORY",
    "C5_PHASES",
    "CATEGORIES",
    "COMPLIANCE_DIR",
    "CONFIG_MARKERS",
    "DASHBOARD_PATH",
    "FINDING_DIR",
    "GC_AGE_DAYS",
    "LEGACY_COMPLIANCE_DIRNAME",
    "LOCK_PATH",
    "MAX_REPORT_RUNS",
    "MAX_SESSION_SUMMARY_RUNS",
    "PLUGIN_TO_PHASE",
    "REPORT_PATH",
    "STATUS_FAIL",
    "STATUS_PASS",
    "STATUS_SKIP",
    "STATUS_WARN",
    "SUMMARY_PATH",
    "TIER_2_CHECK_IDS",
]

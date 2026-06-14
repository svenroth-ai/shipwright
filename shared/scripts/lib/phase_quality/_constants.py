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

# Per-finding JSON dir — ALREADY gitignored (canon block re-excludes it).
FINDING_DIR = f"{COMPLIANCE_DIR}/skill-compliance"
# The 3 aggregate roll-ups are TRANSIENT derived caches of the FINDING_DIR
# JSONs (regenerated every Stop; never tracked; not in audit_staleness.
# DOC_REGISTRY). They live UNDER FINDING_DIR so they inherit the existing
# gitignore rule and never show up as `??` on idle main — completing ADR-089's
# runtime/snapshot split for this producer (iterate-2026-06-09; trg-7640bd14).
# load_findings/gc only glob `*.json`, so the `.md` roll-ups never collide.
REPORT_PATH = f"{FINDING_DIR}/_report.md"
SUMMARY_PATH = f"{FINDING_DIR}/_findings.md"
DASHBOARD_PATH = f"{FINDING_DIR}/_dashboard.md"
LOCK_PATH = ".shipwright/locks/phase-quality.lock"

# Finding status constants.
STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_WARN = "WARN"
STATUS_SKIP = "SKIP"

# Sentinel run_ids — a DEGENERATE audit context (no resolvable run/session).
# ``resolve_run_id`` only yields ``"unknown"`` when session_id is empty AND there
# is no run-config run_id / run_started event / loop var, so a sentinel-run
# finding is "not applicable in this audit context" (mirrors the audit-time
# guard ``tools/verifiers/_iterate_run_id._RUN_ID_SENTINELS``). The rollup VIEWS
# exclude such snapshots (see ``_aggregates.load_actionable_findings``); raw
# ``load_findings`` + ``gc_old_findings`` keep them.
RUN_ID_SENTINELS: frozenset[str] = frozenset({"", "unknown"})


def is_sentinel_run(run_id: str | None) -> bool:
    """True when ``run_id`` is a degenerate-context sentinel (``""`` / ``"unknown"``)."""
    return str(run_id or "").strip().lower() in RUN_ID_SENTINELS


# NOTE: the Shipwright-project marker set + the greenfield/foreign predicate
# live in ``lib.project_root`` (CONFIG_MARKERS / is_shipwright_project) — the
# single source of truth every hook delegates to
# (iterate-2026-06-12-canonical-project-predicate).


__all__ = [
    "C4_PHASES",
    "C5_CATEGORY",
    "C5_PHASES",
    "CATEGORIES",
    "COMPLIANCE_DIR",
    "DASHBOARD_PATH",
    "FINDING_DIR",
    "GC_AGE_DAYS",
    "LEGACY_COMPLIANCE_DIRNAME",
    "LOCK_PATH",
    "MAX_REPORT_RUNS",
    "MAX_SESSION_SUMMARY_RUNS",
    "PLUGIN_TO_PHASE",
    "REPORT_PATH",
    "RUN_ID_SENTINELS",
    "STATUS_FAIL",
    "STATUS_PASS",
    "STATUS_SKIP",
    "STATUS_WARN",
    "SUMMARY_PATH",
    "TIER_2_CHECK_IDS",
    "is_sentinel_run",
]

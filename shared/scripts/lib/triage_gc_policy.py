"""Machine-churn policy vocabulary for the triage GC engine.

Split out of :mod:`lib.triage_gc_core` (which crossed the 300-LOC guideline
when it grew an `amend` overlay for iterate-2026-08-08-triage-amend-event) so
the policy VOCABULARY — which token pairs count as pure machine churn — lives
apart from the engine MECHANICS (resolve/plan/apply/validate). Re-exported
from :mod:`lib.triage_gc_core`, which is in turn re-exported from
``tools/triage_gc.py``, so every historical import path
(``from lib.triage_gc_core import is_machine_churn``, ``from tools.triage_gc
import MACHINE_DISMISSERS``, ...) is unchanged.

Policy (decided 2026-06-05): **machine-churn ONLY** — see
:func:`is_machine_churn`. The dismissed pile is ~half human-curated
(re-prioritisations, "resolved by PR #N", supersessions); that is real audit
history and is kept, as are ``promoted`` and open items. Both conditions must
hold, so a human dismissal reusing a token survives.
"""

from __future__ import annotations

# Pure background-producer dismissers (NOT user/operator/webui/cli/manual).
MACHINE_DISMISSERS = frozenset({
    "sbomGenerator",
    "auditDetector",
    "driftDetector",
    "f05Detector",  # legacy: F0.5 triage producer removed 2026-06-13; kept for historical dismissals
    "githubImporter",
    "complianceBacklog",
    "phaseQualityBacklog",  # phase_quality _triage_bundle producer
    "testEvidence",         # shipwright-compliance test_evidence producer
    "acceptedRiskConverger",  # tools/accepted_risks_converge (register -> surfaces)
})

# Exact machine auto-resolve tokens. A human free-text reason (even one that
# starts with one of these) will not match — exact equality only.
MACHINE_REASONS = frozenset({
    "sbomResolved",
    "auditResolved",  # legacy: pre-bundle audit dismissals; no current emitter (audit now → complianceBacklog)
    "driftResolved",
    "f05Resolved",  # legacy: F0.5 triage producer removed 2026-06-13; kept for historical churn
    "githubResolved",
    "complianceResolved",
    "complianceRefreshed",  # stale-signature backlog rollup superseded (triage_bundle ~L165)
    "phaseQualityResolved",
    "phaseQualityRefreshed",  # F30: stale-signature phase-quality rollup superseded (phase_quality/_triage_bundle ~L268)
    "testEvidenceResolved",
    "prChecksResolved",  # github_triage PR-CI: a tracked PR's failing checks went green (resolve_pr_ci, by=githubImporter). prMerged/prClosed are terminal lifecycle markers, kept as history (not *Resolved churn).
    "acceptedRiskResolved",  # accepted_risks_converge: a local-scanner finding is covered by a register acceptance. Recurring — ingest suppression cannot retract an item filed BEFORE the acceptance, and each re-scan refiles it once dismissed, so this is churn and must be GC'd.
})


def is_machine_churn(item: dict) -> bool:
    """True iff ``item`` is a pure producer auto-resolve dismissal."""
    return (
        item.get("status") == "dismissed"
        and item.get("statusBy") in MACHINE_DISMISSERS
        and item.get("statusReason") in MACHINE_REASONS
    )

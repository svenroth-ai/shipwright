"""BP-2 change reconciliation: which behavior-touched FRs were re-verified.

Single SSOT shared by the Control-Grade reconciliation dimension
(:func:`_control_block.build_grade_inputs`) and — from cc3 (AR-05) — the RTM
"Reconciled?" column, so the grade dimension and the matrix can never disagree.

An FR is **behavior-touched** when an event records a behavior-affecting impact
for it: from the per-FR ``fr_impact`` map (BP-2) when present, else the
event-level ``spec_impact`` applied to the event's ``affected_frs``/``new_frs``
(the fallback that lets pre-BP-2 events still contribute). An FR is
**reconciled** when a tested event (``tests_total > 0``) that references it
occurs at or after its latest behavior-affecting touch. Reconciliation keys on
*touched-without-re-verify*, **never on age** — an old but re-verified change is
reconciled forever.

Loads the behavior-affecting predicate from the shared FR-classification SSOT
(pollution-free via ``audit_adapters.load_shared_lib``, mirroring
:mod:`scripts.lib._traceability`) so "behavior-affecting" is defined once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from scripts.audit.audit_adapters import load_shared_lib

_fc = load_shared_lib("fr_classification")

RECONCILED = "reconciled"
NEEDS_REVERIFICATION = "needs_reverification"
UNTOUCHED = "untouched"


@dataclass
class Reconciliation:
    """Per-FR reconciliation status. Only behavior-touched FRs are present;
    every other FR reads as :data:`UNTOUCHED`."""

    statuses: dict[str, str] = field(default_factory=dict)

    def status(self, fr_id: str) -> str:
        """Reconciliation status for one FR (cc3 RTM per-row helper)."""
        return self.statuses.get(fr_id, UNTOUCHED)

    @property
    def behavior_touched(self) -> set[str]:
        return set(self.statuses)

    @property
    def unreconciled(self) -> set[str]:
        return {fr for fr, s in self.statuses.items() if s == NEEDS_REVERIFICATION}


def _parse_ts(ts) -> datetime | None:
    """Parse an ISO-8601 timestamp; ``None`` on malformed input (skipped)."""
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None


def _referenced_and_touched(we) -> tuple[set[str], set[str]]:
    """Return ``(referenced_frs, behavior_touched_frs)`` for one work event.

    ``referenced`` = every FR the event names (affected/new/fr_impact keys) — a
    tested such event re-verifies those FRs. ``touched`` = the behavior-affecting
    subset (per-FR map, or the event-level spec_impact fallback). A present
    (non-empty) ``fr_impact`` map is authoritative: an ``affected_frs`` entry
    absent from it is NOT behavior-touched even under a behavior-affecting
    event-level ``spec_impact`` (the fallback applies only when the map is
    absent/empty)."""
    referenced = {fr for fr in (getattr(we, "affected_frs", None) or []) if fr}
    referenced |= {fr for fr in (getattr(we, "new_frs", None) or []) if fr}
    fr_impact = getattr(we, "fr_impact", None) or {}
    if fr_impact:
        referenced |= {fr for fr in fr_impact if fr}
        touched = {
            fr for fr, impact in fr_impact.items()
            if fr and _fc.is_behavior_affecting(impact)
        }
        return referenced, touched
    # Fallback: a behavior-affecting event-level spec_impact touches every FR
    # the (pre-BP-2) event references.
    if _fc.is_behavior_affecting(getattr(we, "spec_impact", "")):
        return referenced, set(referenced)
    return referenced, set()


def compute_reconciliation(work_events) -> Reconciliation:
    """Compute per-FR reconciliation status from the work-event log.

    Deterministic for a given log: for each FR, the latest behavior-affecting
    touch is reconciled iff some tested event referencing it occurs at or after
    that touch. FRs never behavior-touched are absent (read as untouched)."""
    latest_touch: dict[str, datetime] = {}
    latest_verify: dict[str, datetime] = {}
    for we in work_events:
        dt = _parse_ts(getattr(we, "timestamp", ""))
        if dt is None:
            continue
        referenced, touched = _referenced_and_touched(we)
        for fr in touched:
            if fr not in latest_touch or dt > latest_touch[fr]:
                latest_touch[fr] = dt
        if (getattr(we, "tests_total", 0) or 0) > 0:
            for fr in referenced:
                if fr not in latest_verify or dt > latest_verify[fr]:
                    latest_verify[fr] = dt
    statuses: dict[str, str] = {}
    for fr, touch_dt in latest_touch.items():
        verify_dt = latest_verify.get(fr)
        statuses[fr] = (
            RECONCILED
            if verify_dt is not None and verify_dt >= touch_dt
            else NEEDS_REVERIFICATION
        )
    return Reconciliation(statuses)

"""WP9 (2026-06-10 deep audit) — triage_gc hardening: F30 + F19.

F30: ``triage_gc.MACHINE_REASONS`` was missing ``phaseQualityRefreshed`` (the
phase-quality ``_triage_bundle`` emits it on every signature change) → that
per-run dismissal churn was never GC'd. Same decoupled-SSoT miss the
``complianceRefreshed`` fix already closed. Includes a registry-driven
forward+reverse-drift meta-test so the SSoT can't silently drift again.

F19: the GC plan was computed OUTSIDE the lock; ``apply_gc`` dropped every line
for a planned id — including a status flip appended between plan and apply
(TOCTOU → lost operator decision). ``apply_gc`` now recomputes under the lock
and intersects with the caller's plan.

Lives in its own module (separate from ``test_triage_gc.py``) to keep both
files under the bloat LOC guideline — these are new WP9 cases, not edits to the
grandfathered suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import triage  # noqa: E402
import triage_gc  # noqa: E402


def _add(root: Path, *, title: str, dedup: str) -> str:
    return triage.append_triage_item(
        root, source="sbom", severity="low", kind="compliance",
        title=title, detail="d", dedup_key=dedup,
    )


def _dismiss(root: Path, item_id: str, *, by: str, reason: str) -> None:
    triage.mark_status(root, item_id, new_status="dismissed", by=by, reason=reason)


# --------------------------------------------------------------------------
# F30 — phaseQualityRefreshed is machine-churn and must be GC-able
# --------------------------------------------------------------------------

def test_phasequality_refreshed_machine_churn_dropped(tmp_path: Path):
    """The phaseQuality producer emits BOTH ``phaseQualityResolved`` (all fails
    cleared) AND ``phaseQualityRefreshed`` (stale-signature rollup superseded by
    a fresh signature — ``phase_quality/_triage_bundle`` ~L268). Identical
    decoupled-SSoT miss to the ``complianceRefreshed`` fix: the refresh token was
    absent from MACHINE_REASONS, so this pure machine-churn accumulated as kept
    noise."""
    resolved = _add(tmp_path, title="resolved", dedup="kpr")
    _dismiss(tmp_path, resolved, by="phaseQualityBacklog", reason="phaseQualityResolved")
    refreshed = _add(tmp_path, title="refreshed", dedup="kpf")
    _dismiss(tmp_path, refreshed, by="phaseQualityBacklog", reason="phaseQualityRefreshed")
    human = _add(tmp_path, title="h", dedup="khp")
    _dismiss(tmp_path, human, by="user", reason="phaseQualityRefreshed")  # human → kept
    assert triage_gc.plan_gc(tmp_path)["drop_ids"] == {resolved, refreshed}


# --------------------------------------------------------------------------
# F30 forward+reverse-drift meta-test — registry-driven SSoT
# --------------------------------------------------------------------------

# The canonical set of RECURRING machine auto-resolve tokens each background
# producer emits. This is the SSoT MACHINE_REASONS must stay aligned with: a
# producer that gains a new recurring auto-resolve token must add it here AND to
# triage_gc.MACHINE_REASONS, or the meta-test fails — closing the decoupled-SSoT
# gap that left phaseQualityRefreshed (F30) and complianceRefreshed uncollected.
# One-shot retirement tokens (e.g. compliance's supersededByBacklog, AC-4 of the
# 2026-05-31 bundle) are deliberately EXCLUDED: they fire once per legacy item,
# not every run, so they are real audit history, not churn.
PRODUCER_RECURRING_DISMISS_TOKENS = frozenset({
    "sbomResolved",          # sbom_generator
    "auditResolved",         # audit_detector
    "driftResolved",         # drift detector
    "f05Resolved",           # f0.5 surface verification
    "githubResolved",        # github importer
    "complianceResolved",    # compliance backlog (triage_bundle)
    "complianceRefreshed",   # compliance backlog (stale-signature rollup)
    "phaseQualityResolved",  # phase-quality backlog (_triage_bundle)
    "phaseQualityRefreshed",  # phase-quality backlog (stale-signature rollup)
    "testEvidenceResolved",  # test-evidence
})


def test_machine_reasons_covers_every_producer_recurring_token():
    """Forward-drift guard: every recurring producer auto-resolve token MUST be
    in MACHINE_REASONS, else that producer's per-run churn is never GC'd (the
    F30 / complianceRefreshed failure mode)."""
    missing = PRODUCER_RECURRING_DISMISS_TOKENS - triage_gc.MACHINE_REASONS
    assert not missing, (
        f"producer recurring dismiss tokens not in MACHINE_REASONS: {sorted(missing)} "
        "— add them or the per-run churn accumulates unbounded in tracked history"
    )


def test_machine_reasons_has_no_unknown_tokens():
    """Reverse-drift guard: MACHINE_REASONS must not carry a token no producer
    emits (a stale token GC's nothing and hides drift in the other direction)."""
    unknown = triage_gc.MACHINE_REASONS - PRODUCER_RECURRING_DISMISS_TOKENS
    assert not unknown, (
        f"MACHINE_REASONS carries tokens no producer emits: {sorted(unknown)} "
        "— remove them or register the producer token above"
    )


def test_machine_reasons_phasequality_refreshed_present():
    """Pin the specific F30 token so a future MACHINE_REASONS edit can't silently
    drop it without a red test."""
    assert "phaseQualityRefreshed" in triage_gc.MACHINE_REASONS


# --------------------------------------------------------------------------
# F19 — TOCTOU: a status flip appended between plan and apply must survive.
# --------------------------------------------------------------------------

def test_apply_recomputes_plan_under_lock_preserving_concurrent_reopen(tmp_path: Path):
    """A status flip appended BETWEEN plan and apply must survive ``apply_gc``.

    Repro: ``plan_gc`` marks item ``m`` droppable (machine-churn dismissed).
    Before ``apply_gc`` runs, the WebUI / a producer re-opens ``m`` (status →
    ``triage``). The stale ``drop_ids`` would delete every line for ``m`` —
    including the fresh re-open — wiping the operator decision. The fix
    recomputes under the lock, so a no-longer-machine-churn item is NOT dropped.
    """
    m = _add(tmp_path, title="m", dedup="k1")
    _dismiss(tmp_path, m, by="auditDetector", reason="auditResolved")
    keep_dropped = _add(tmp_path, title="still-churn", dedup="k2")
    _dismiss(tmp_path, keep_dropped, by="sbomGenerator", reason="sbomResolved")

    stale_plan = triage_gc.plan_gc(tmp_path)
    assert stale_plan["drop_ids"] == {m, keep_dropped}

    # CONCURRENT re-open of m between plan and apply (operator/WebUI decision).
    triage.mark_status(tmp_path, m, new_status="triage", by="user",
                       reason="re-opened: actually a real finding")

    triage_gc.apply_gc(tmp_path, stale_plan["drop_ids"])

    survivors = {i["id"]: i for i in triage.read_all_items(tmp_path)}
    assert m in survivors, "F19 TOCTOU: concurrent re-open was dropped by apply_gc"
    assert survivors[m]["status"] == "triage"
    assert keep_dropped not in survivors


def test_apply_does_not_drop_item_churned_after_the_consented_plan(tmp_path: Path):
    """Consent-surface guard: apply drops the INTERSECTION of the fresh plan and
    the caller's planned ids — never MORE than the dry-run report announced.

    An item that becomes machine-churn AFTER the operator saw the plan was never
    in the report they consented to, so apply must NOT silently drop it (it is
    GC'd on the NEXT run, when it appears in a fresh report)."""
    m = _add(tmp_path, title="m", dedup="k1")
    stale_plan = triage_gc.plan_gc(tmp_path)
    assert stale_plan["drop_ids"] == set()
    _dismiss(tmp_path, m, by="auditDetector", reason="auditResolved")
    triage_gc.apply_gc(tmp_path, stale_plan["drop_ids"])
    survivors = {i["id"] for i in triage.read_all_items(tmp_path)}
    assert m in survivors
    assert triage_gc.plan_gc(tmp_path)["drop_ids"] == {m}

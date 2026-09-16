"""Result shape + operator-facing warnings for :mod:`layer_promotion_sweep`.

Split out purely to keep that module under the file-size guideline — mirrors
the existing ``lib.sweep_result`` split for the sibling outbox sweep.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LayerPromotionSweepResult:
    """Outcome of :func:`layer_promotion_sweep.run_layer_promotion_sweep`.

    ``status`` in {``delivered``, ``not_delivered``, ``no_change``,
    ``skipped``, ``error``, ``rollback_failed``}. ``skipped`` covers every
    case this sweep could not even EVALUATE (no manifest, no network, no CI
    evidence yet, an opt-out) — never alarming, always the routine steady
    state for most projects most of the time, and silent in
    :func:`sweep_warnings`. ``no_change`` means the tool decided and there
    was genuinely nothing to promote — also silent. ``not_delivered`` means
    a promotion WAS found and committed locally, but shipping it as its own
    PR did not complete this run (an equivalent PR is already open, the push
    was rejected, or ``gh pr create`` failed) — worth a line, never
    alarming: the local commit is always rolled back regardless (see
    ``lib.layer_promotion_delivery``), so nothing is lost, only deferred to
    the next run. ``error`` is reserved for something THIS wiring itself
    could not do to its OWN local git state before delivery was even
    attempted (stage/commit, or unparseable tool output) — the underlying
    tool decided fine, but recording its output failed; every such path
    also best-effort rolls the worktree back to ``pre_sha`` so no staged
    residue survives into a later, unrelated commit. ``rollback_failed`` is
    the loud, distinct case: the promotion commit was pushed for delivery
    but the guaranteed reset back to ``pre_sha`` itself did not succeed
    (unreadable ``pre_sha``, or the reset call itself failed/timed out) — the
    one outcome where the commit may still be sitting on the iterate's own
    branch, so this is never silent. ``delivered`` means a fresh PR was
    opened this run.
    """

    status: str
    reason: str = ""
    promoted: list[str] = field(default_factory=list)
    escalated: int = 0
    pr_url: str = ""
    branch: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "promoted": self.promoted,
            "escalated": self.escalated,
            "pr_url": self.pr_url,
            "branch": self.branch,
        }


def sweep_warnings(result: LayerPromotionSweepResult) -> list[str]:
    """Operator-facing notes — mirrors ``lib.sweep_result.sweep_warnings``'
    counts-only shape. Reports every outcome where something was actually
    FOUND (delivered, not-yet-delivered, or a recording error) plus any
    standing escalation. ``skipped`` (nothing could even be evaluated) and
    ``no_change`` (evaluated, nothing to promote) both stay silent — those
    are the routine steady state for most projects most of the time."""
    notes: list[str] = []
    if result.status == "rollback_failed":
        notes.append(
            "layer-promotion-sweep CRITICAL: promotion commit may still be on "
            f"this branch — rollback failed: {result.reason}"
        )
    if result.status == "error":
        notes.append(f"layer-promotion-sweep error: {result.reason}")
    if result.status == "not_delivered":
        notes.append(f"layer-promotion-sweep found a promotion but did not ship it: {result.reason}")
    if result.status == "delivered":
        detail = f" ({result.pr_url})" if result.pr_url else ""
        notes.append(
            f"layer-promotion-sweep opened its own PR promoting "
            f"{len(result.promoted)} FR Layer cell(s) from confirmed CI "
            f"evidence: {', '.join(result.promoted)}{detail}"
        )
    if result.escalated:
        notes.append(
            f"layer-promotion-sweep left {result.escalated} FR(s) escalated — "
            "an operator decision is needed via record_layer_promotion_decision.py"
        )
    return notes


__all__ = ["LayerPromotionSweepResult", "sweep_warnings"]

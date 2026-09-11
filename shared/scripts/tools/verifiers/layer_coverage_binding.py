"""``check_binding_completeness`` — the CheckResult wrapper for P3.3's binding-
completeness gate. Split from ``layer_coverage`` (300-LOC cap) at the moment this
landed; the pure evaluator (:mod:`_layer_coverage_binding`) already lives in its
own module by the same precedent, so the wrapper follows it rather than growing
the file two of the three siblings already had to split away from.

Reuses ``layer_coverage``'s own infra plumbing (complexity gating, git precheck,
infra-error shaping) rather than duplicating it — the same private-import pattern
``_layer_coverage_removal`` already uses on ``_layer_coverage_core``.
"""

from __future__ import annotations

from pathlib import Path

from . import layer_coverage as _lc
from ._layer_coverage_ac import changed_criteria_ids
from ._layer_coverage_binding import evaluate_binding_completeness
from ._layer_coverage_core import CrossLayerVerdict
from ._layer_coverage_regen import _merge_base, regenerate_base_head
from ._layer_coverage_rollout import rollout_manifest
from .common import CheckResult, Severity

_NAME = "binding completeness (behaviour change → binding names the highest observed layer)"


def check_binding_completeness(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    """Same scope/cost floor as ``check_cross_layer_coverage`` (medium+, base+head
    regenerated WITH this run's execution evidence) since it judges the identical
    behaviour-changed FR set — each behaviour-changed FR's declared binding must
    name the highest layer this run's OWN evidence proves executed-passing."""
    name = _NAME
    complexity = _lc._complexity(project_root, run_id)
    if not _lc._is_enforcing(complexity):
        return _lc._skip(name, f"skipped (complexity={complexity or 'unknown'})")
    if not commit_hash:
        return _lc._infra_result(name, complexity, "no --commit supplied")
    precheck = _lc._git_precheck(name, project_root, complexity)
    if precheck is not None:
        return precheck
    try:
        regen = regenerate_base_head(project_root, commit_hash, with_evidence=True, run_id=run_id)
        if regen is None:
            return _lc._infra_result(name, complexity, "git unavailable / no base ref / collector unavailable")
        base, head, _renames = regen
        ac_changed, ac_error = changed_criteria_ids(
            project_root, _merge_base(project_root, commit_hash), commit_hash, base, head,
        )
        if ac_error:
            return _lc._infra_result(name, complexity, ac_error)
        verdict = evaluate_binding_completeness(base, head, ac_changed)
        if verdict.hard:
            # Lazy: the rollout snapshot is a full archive+build of a third,
            # potentially old commit (same cost class as the base/head builds
            # above) — only worth paying when there is a candidate HARD gap
            # for it to possibly downgrade (trg-aedcfe7b transition rule).
            # `rollout_manifest` never raises (see its own docstring), so a
            # failure here degrades to `None` (no grace), never an infra error.
            rollout = rollout_manifest(project_root, commit_hash)
            if rollout is not None:
                verdict = evaluate_binding_completeness(base, head, ac_changed, rollout)
    except Exception as exc:  # noqa: BLE001 — surface as ERROR at medium+, never a silent crash
        return _lc._infra_result(name, complexity, f"regeneration error: {type(exc).__name__}")
    return _binding_result(name, verdict)


def _advisory_tag(gap) -> str:
    """The per-gap parenthetical in an advisory message: the transition rule
    (trg-aedcfe7b) downgrades a HARD gap without changing ``source`` (an
    ``explicit``-sourced gap can now land in ``advisory`` too), so reusing
    ``g.source`` verbatim there would misleadingly read as if the FR were
    legacy-sourced. Every other advisory reason (legacy source, collision)
    keeps printing the real ``source`` value, unchanged from before this
    rule existed."""
    if gap.reason == "BINDING_INCOMPLETE_TRANSITION":
        return "pre-rollout transition grace"
    return gap.source


def _binding_result(name: str, verdict: CrossLayerVerdict) -> CheckResult:
    if not verdict.changed_keys:
        return CheckResult(name, True, "no behaviour-changed FR (no spec/AC/FR delta)")
    if verdict.any_fail:
        gaps = "; ".join(f"{g.display}: omits {g.layer}" for g in verdict.hard[:6])
        if len(verdict.hard) > 6:
            gaps += f" (+{len(verdict.hard) - 6} more)"
        return CheckResult(
            name, False,
            f"{len(verdict.hard)} behaviour-changed FR(s) have higher-layer evidence than their "
            "binding names: " + gaps + "  →  widen the FR's Layers cell to the "
            "highest layer a test actually proved passing",
        )
    if verdict.advisory:
        gaps = "; ".join(f"{g.display}: omits {g.layer} ({_advisory_tag(g)})" for g in verdict.advisory[:6])
        if len(verdict.advisory) > 6:
            gaps += f" (+{len(verdict.advisory) - 6} more)"
        return CheckResult(
            name, False,
            f"{len(verdict.advisory)} FR(s) have higher-layer evidence than their binding names "
            "but are legacy/collision/pre-rollout (advisory): " + gaps,
            severity=Severity.WARNING.value, strict_exempt=True,
        )
    return CheckResult(
        name, True, f"{len(verdict.changed_keys)} behaviour-changed FR(s): binding is complete",
    )


__all__ = ["check_binding_completeness"]

"""Control Grade — deterministic A–F control-posture score for a repository.

This is the keystone scoring function behind (a) the dashboard's Control
Verdict block, (b) the future public repo-grader (lead magnet), and (c) the
certification gate. It is therefore written **repo-agnostic**: the scoring
operates purely over a normalized :class:`GradeInputs` value, with no
dependency on Shipwright's collectors. A thin adapter
(:func:`grade_from_compliance_data`) maps this project's ``ComplianceData``
onto ``GradeInputs``; a future generic-grader plugin populates the same
struct from any repo's data and reuses ``compute_grade`` unchanged.

Methodology — *modeled on* **OpenSSF Scorecard** (Apache-2.0): the aggregate is
an importance-weighted average of per-dimension [0, 1] scores, and a dimension
that cannot be evaluated is excluded from the denominator (Scorecard's ``-1``
"inconclusive" convention) rather than scored 0. If no dimension can be measured
the result is "Not Gradeable" — never an unearned ``F``. A measurable-but-poor
dimension *does* score low and *does* count: ``failed != n/a``. Each dimension
carries an ``anchor`` naming the recognized **open** standard it follows
(ISO/IEC/IEEE 29148/12207, SLSA, NIST SSDF, OWASP, ISO/IEC 25010, OpenSSF
Scorecard), so the rubric is defensible rather than bespoke — and a CI dashboard
deliberately does *not* borrow safety-certification (DO-178C/IEC 62304)
vocabulary it cannot honestly claim.

The raw average is then passed through :mod:`scripts.lib._grade_gate` (the
honesty layer): a self-relative traceability decline depresses the requirement
dimension, and the headline is capped below "A — full control" when a
load-bearing pillar is declining, dark-but-expected, or broken — so the headline
can't lie while the per-dimension table keeps the full detail.
"""

from __future__ import annotations

from scripts.lib._grade_gate import (
    apply_traceability_penalty,
    apply_verdict_gate,
)
from scripts.lib._grade_types import DimensionResult, GradeInputs, GradeReport

# Re-export the value model so external callers keep importing it from here.
__all__ = ["GradeInputs", "DimensionResult", "GradeReport", "compute_grade"]


# --- Bands (per the agreed rubric; 50-point F-floor has SQALE precedent) ----
# (min_score_inclusive, letter, plain-language verdict mapped 1:1 — no drift).
_BANDS: list[tuple[float, str, str]] = [
    (90.0, "A", "Under full control."),
    (80.0, "B", "Controlled, minor gaps."),
    (70.0, "C", "Mostly controlled — verification gaps."),
    (50.0, "D", "Weak control — untraceable or untested changes."),
    (0.0, "F", "Out of control — AI changes you can't verify."),
]

_NOT_GRADEABLE_VERDICT = (
    "Not gradeable — no control dimension could be measured for this repository."
)


def _ratio(num: int, den: int) -> float:
    """Clamped num/den in [0, 1]; 0 when den <= 0."""
    if den <= 0:
        return 0.0
    return max(0.0, min(1.0, num / den))


def _score_dimensions(inp: GradeInputs) -> list[DimensionResult]:
    """Compute each dimension's [0, 1] score (or None when not measurable)."""
    dims: list[DimensionResult] = []

    # 1. Requirement traceability (25%) — coverage + change classification.
    if inp.frs_total > 0:
        coverage = _ratio(inp.frs_covered, inp.frs_total)
        tag_rate = (
            _ratio(inp.events_fr_tagged, inp.events_total)
            if inp.events_total > 0 else 1.0
        )
        req_score: float | None = 0.6 * coverage + 0.4 * tag_rate
        req_detail = (
            f"{inp.frs_covered}/{inp.frs_total} FRs covered; "
            f"{inp.events_fr_tagged}/{inp.events_total} changes traced "
            "(FR-linked or classified no-FR)"
        )
        # Honesty gate: a self-relative FR-tag decline depresses this dimension
        # (capped) so a broad "classified no-FR" credit can't mask a freeze.
        req_score, _decline_suffix = apply_traceability_penalty(req_score, inp)
        req_detail += _decline_suffix
    else:
        req_score, req_detail = None, "no requirements declared"
    dims.append(DimensionResult(
        "requirement_traceability", "Requirement traceability", 0.25,
        req_score, "requirement-to-work traceability (ISO/IEC/IEEE 29148)",
        req_detail,
    ))

    # 2. Test health (20%) — latest *full* suite pass-ratio.
    if inp.latest_full_suite_total:
        th_score: float | None = _ratio(
            inp.latest_full_suite_passed or 0, inp.latest_full_suite_total)
        th_detail = (
            f"latest full suite {inp.latest_full_suite_passed}/"
            f"{inp.latest_full_suite_total}"
            + (f" ({inp.latest_full_suite_date})"
               if inp.latest_full_suite_date else "")
        )
    else:
        th_score, th_detail = None, "no full suite run recorded"
    dims.append(DimensionResult(
        "test_health", "Test health", 0.20,
        th_score, "automated tests pass (OpenSSF Scorecard)", th_detail,
    ))

    # 3. Change traceability (15%) — provenance to commit/ADR/test.
    if inp.events_total > 0:
        ct_score: float | None = _ratio(
            inp.events_with_provenance, inp.events_total)
        ct_detail = (
            f"{inp.events_with_provenance}/{inp.events_total} changes "
            "linked to a commit, ADR or test run"
        )
    else:
        ct_score, ct_detail = None, "no change events recorded"
    dims.append(DimensionResult(
        "change_traceability", "Change traceability", 0.15,
        ct_score, "change provenance (SLSA)", ct_detail,
    ))

    # 4. Change reconciliation (15%) — needs BP-2 behavior-affecting impact.
    if inp.reconciliation_measurable:
        if inp.frs_behavior_touched > 0:
            rec_score: float | None = _ratio(
                inp.frs_behavior_touched - inp.frs_unreconciled,
                inp.frs_behavior_touched)
            rec_detail = (
                f"{inp.frs_unreconciled}/{inp.frs_behavior_touched} "
                "behavior-touched FRs not re-verified"
            )
        else:
            rec_score, rec_detail = 1.0, "no behavior-affecting FR touches"
    else:
        rec_score = None
        rec_detail = "not measurable — needs per-change behavior-impact (BP-2)"
    dims.append(DimensionResult(
        "change_reconciliation", "Change reconciliation", 0.15,
        rec_score, "re-verify changed requirements (ISO/IEC/IEEE 12207)",
        rec_detail,
    ))

    # 5. Security (10%) — open high/critical from a trustworthy scan.
    if inp.security_measurable and inp.security_open_high_critical is not None:
        open_hc = inp.security_open_high_critical
        sec_score: float | None = (
            1.0 if open_hc == 0 else min(1.0, max(0.0, 1.0 - 0.34 * open_hc)))
        sec_detail = f"{open_hc} open high/critical"
    else:
        sec_score = None
        sec_detail = "no trustworthy local scan (see CI security gate)"
    dims.append(DimensionResult(
        "security", "Security", 0.10,
        sec_score, "no open high/critical vulns (NIST SSDF)", sec_detail,
    ))

    # 6. Size / maintainability (10%) — net ratchet growth (delta <= 0 good).
    if inp.bloat_ratchet_delta is not None:
        delta = inp.bloat_ratchet_delta
        mt_score: float | None = (
            1.0 if delta <= 0 else max(0.0, 1.0 - delta / 100.0))
        mt_detail = f"ratchet delta {delta:+d} lines (net growth)"
    else:
        mt_score, mt_detail = None, "no size baseline"
    dims.append(DimensionResult(
        "maintainability", "Size / maintainability discipline", 0.10,
        mt_score, "no unchecked code-size growth (ISO/IEC 25010)", mt_detail,
    ))

    # 7. Dependency hygiene (5%) — resolved licenses, 0 copyleft surprises.
    if inp.deps_total > 0:
        base = _ratio(inp.deps_total - inp.deps_unknown_license, inp.deps_total)
        dep_score: float | None = min(1.0, max(0.0, base - 0.1 * inp.deps_copyleft))
        dep_detail = (
            f"{inp.deps_unknown_license} unresolved / {inp.deps_total} "
            f"licenses; {inp.deps_copyleft} copyleft"
        )
    else:
        dep_score, dep_detail = None, "no dependencies declared"
    dims.append(DimensionResult(
        "dependency_hygiene", "Dependency hygiene", 0.05,
        dep_score, "dependency license & risk (OWASP)", dep_detail,
    ))

    return dims


def _band(score: float) -> tuple[str, str]:
    """Map a 0–100 score to (letter, verdict-label)."""
    for threshold, letter, label in _BANDS:
        if score >= threshold:
            return letter, label
    return "F", _BANDS[-1][2]


def compute_grade(inp: GradeInputs) -> GradeReport:
    """Compute the Control Grade deterministically from ``inp``.

    Aggregation follows OpenSSF Scorecard: weighted average over the
    *measurable* dimensions only (n/a dimensions excluded from the
    denominator). All-n/a ⇒ "Not Gradeable", never a 0/F.
    """
    dims = _score_dimensions(inp)
    measurable = [d for d in dims if d.score is not None]

    if not measurable:
        return GradeReport(
            gradeable=False, score=None, grade="?",
            verdict=_NOT_GRADEABLE_VERDICT, band_label="Not gradeable",
            dimensions=dims, reasons=[], verified_from=inp.verified_from,
        )

    total_weight = sum(d.weight for d in measurable)
    weighted = sum(d.weight * d.score for d in measurable)
    # Clamp to [0, 100] — dimension scores are already [0, 1], this makes the
    # contract explicit and bulletproof against out-of-range adapter inputs.
    raw_score = max(0.0, min(100.0, round(weighted / total_weight * 100.0, 1)))

    # Honesty gate: cap the headline (score + letter together) when a
    # load-bearing pillar is declining, dark-but-expected, or broken. The number
    # stays the weighted average unless a gate condition fires.
    ceiling, gate_reasons = apply_verdict_gate(inp, dims, raw_score)
    score100 = min(raw_score, ceiling)
    grade, band_label = _band(score100)
    # The gate only owns the headline when it actually lowered it; a non-binding
    # condition (raw already below the ceiling) must not claim "Capped:".
    gate_binding = bool(gate_reasons) and ceiling < raw_score

    # Top reasons: when the gate capped the headline its why leads (it explains
    # the cap); otherwise the dimensions that lost the most weighted points —
    # capped at three total.
    losers = sorted(
        (d for d in measurable if d.weighted_loss > 0),
        key=lambda d: d.weighted_loss, reverse=True,
    )
    loser_reasons = [f"{d.label}: {d.detail}" for d in losers]
    if gate_binding:
        reasons = (gate_reasons + loser_reasons)[:3]
        verdict = f"{band_label} Capped: {gate_reasons[0]}."
    else:
        reasons = loser_reasons[:3]
        verdict = band_label
        if losers:
            verdict = f"{band_label} Primarily capped by {losers[0].label.lower()}."

    return GradeReport(
        gradeable=True, score=score100, grade=grade, verdict=verdict,
        band_label=band_label, dimensions=dims, reasons=reasons,
        verified_from=inp.verified_from,
    )

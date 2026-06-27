"""Control Grade — deterministic A–F control-posture score for a repository.

This is the keystone scoring function behind (a) the dashboard's Control
Verdict block, (b) the future public repo-grader (lead magnet), and (c) the
certification gate. It is therefore written **repo-agnostic**: the scoring
operates purely over a normalized :class:`GradeInputs` value, with no
dependency on Shipwright's collectors. A thin adapter
(:func:`grade_from_compliance_data`) maps this project's ``ComplianceData``
onto ``GradeInputs``; a future generic-grader plugin populates the same
struct from any repo's data and reuses ``compute_grade`` unchanged.

Methodology — *in Anlehnung an* **OpenSSF Scorecard** (Apache-2.0): the
aggregate is an importance-weighted average of per-dimension [0, 1] scores,
and a dimension that cannot be evaluated is excluded from the denominator
(Scorecard's ``-1`` "inconclusive" convention) rather than scored 0. If no
dimension can be measured the result is "Not Gradeable" — never an unearned
``F``. A measurable-but-poor dimension *does* score low and *does* count:
``failed != n/a``. Each dimension carries an ``anchor`` naming the recognized
standard it follows (DO-178C/RTM, SLSA, NIST SSDF, OWASP, ISO 25010), so the
rubric is defensible rather than bespoke.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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

# Status thresholds for the per-dimension marker.
_OK_THRESHOLD = 0.9


@dataclass
class GradeInputs:
    """Normalized, repo-agnostic inputs for :func:`compute_grade`.

    Every field is a plain count/flag so any grader (Shipwright or the
    future generic plugin) can populate it. ``None`` on an optional signal
    means "not measurable here" → that dimension is excluded from the score.
    """

    # Requirement traceability
    frs_total: int = 0
    frs_covered: int = 0
    events_total: int = 0
    events_fr_tagged: int = 0
    # Test health (latest *full* suite, not the last event)
    latest_full_suite_passed: int | None = None
    latest_full_suite_total: int | None = None
    latest_full_suite_date: str = ""
    # Change → commit/ADR/test provenance
    events_with_provenance: int = 0
    # Change reconciliation (BP-2 — behavior-affecting impact persisted)
    reconciliation_measurable: bool = False
    frs_behavior_touched: int = 0
    frs_unreconciled: int = 0
    # Security (None → no trustworthy local signal; see AR-10 CI ingest)
    security_measurable: bool = False
    security_open_high_critical: int | None = None
    # Size / maintainability (net ratchet growth; None → no baseline)
    bloat_ratchet_delta: int | None = None
    # Dependency hygiene
    deps_total: int = 0
    deps_unknown_license: int = 0
    deps_copyleft: int = 0
    # Provenance stamp (for reproducibility, per Scorecard Version/SHA/Date)
    verified_from: str = ""


@dataclass
class DimensionResult:
    """One scored dimension. ``score is None`` ⇒ excluded (n/a)."""

    key: str
    label: str
    weight: float
    score: float | None
    anchor: str
    detail: str

    @property
    def status(self) -> str:
        if self.score is None:
            return "n/a"
        return "ok" if self.score >= _OK_THRESHOLD else "gap"

    @property
    def weighted_loss(self) -> float:
        """Points (in weight units) lost — drives the 'top reasons' list."""
        if self.score is None:
            return 0.0
        return self.weight * (1.0 - self.score)


@dataclass
class GradeReport:
    """Result of a grade computation."""

    gradeable: bool
    score: float | None          # 0–100, or None when not gradeable
    grade: str                   # "A".."F", or "?" when not gradeable
    verdict: str
    band_label: str
    dimensions: list[DimensionResult] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    verified_from: str = ""


def _ratio(num: int, den: int) -> float:
    """Clamped num/den in [0, 1]; 0 when den <= 0."""
    if den <= 0:
        return 0.0
    return max(0.0, min(1.0, num / den))


def _score_dimensions(inp: GradeInputs) -> list[DimensionResult]:
    """Compute each dimension's [0, 1] score (or None when not measurable)."""
    dims: list[DimensionResult] = []

    # 1. Requirement traceability (25%) — coverage + active FR-tagging.
    if inp.frs_total > 0:
        coverage = _ratio(inp.frs_covered, inp.frs_total)
        tag_rate = (
            _ratio(inp.events_fr_tagged, inp.events_total)
            if inp.events_total > 0 else 1.0
        )
        req_score: float | None = 0.6 * coverage + 0.4 * tag_rate
        req_detail = (
            f"{inp.frs_covered}/{inp.frs_total} FRs covered; "
            f"{inp.events_fr_tagged}/{inp.events_total} changes FR-tagged"
        )
    else:
        req_score, req_detail = None, "no requirements declared"
    dims.append(DimensionResult(
        "requirement_traceability", "Requirement traceability", 0.25,
        req_score, "DO-178C §11.9 / IEC 62304 / ALM RTM", req_detail,
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
        th_score, "coverage gating (SonarQube 'Sonar Way')", th_detail,
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
        ct_score, "SLSA provenance / OpenSSF Code-Review", ct_detail,
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
        rec_score, "ALM suspect-links + DO-178C/ISO 26262 re-verification",
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
        sec_score, "NIST SSDF (SP 800-218) / OWASP / OpenSSF", sec_detail,
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
        mt_score, "ISO 25010 maintainability / SonarQube", mt_detail,
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
        dep_score, "OWASP A06:2021 / OpenSSF Scorecard", dep_detail,
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
    score100 = max(0.0, min(100.0, round(weighted / total_weight * 100.0, 1)))
    grade, band_label = _band(score100)

    # Top 1–3 reasons = dimensions that lost the most weighted points.
    losers = sorted(
        (d for d in measurable if d.weighted_loss > 0),
        key=lambda d: d.weighted_loss, reverse=True,
    )[:3]
    reasons = [f"{d.label}: {d.detail}" for d in losers]

    verdict = band_label
    if losers:
        verdict = f"{band_label} Primarily capped by {losers[0].label.lower()}."

    return GradeReport(
        gradeable=True, score=score100, grade=grade, verdict=verdict,
        band_label=band_label, dimensions=dims, reasons=reasons,
        verified_from=inp.verified_from,
    )

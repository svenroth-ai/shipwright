"""Value model for the Control Grade — the normalized inputs, the per-dimension
result, and the final report.

Split from ``control_grade.py`` (the scoring/aggregation logic) so the kernel
stays within the size limit. These types are re-exported from ``control_grade``
for back-compat, so external callers keep importing ``GradeInputs`` /
``GradeReport`` from there. This module is a leaf (stdlib only) so the gate and
the scorer can both reference the types without an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Status threshold for the per-dimension marker (ok vs gap).
_OK_THRESHOLD = 0.9


@dataclass
class GradeInputs:
    """Normalized, repo-agnostic inputs for :func:`control_grade.compute_grade`.

    Every field is a plain count/flag so any grader (Shipwright or the
    future generic plugin) can populate it. ``None`` on an optional signal
    means "not measurable here" → that dimension is excluded from the score.
    """

    # Requirement traceability
    frs_total: int = 0
    frs_covered: int = 0
    events_total: int = 0
    # Changes *traced* to a requirement decision: FR-linked OR satisfied no-FR
    # (adapter decides; see _traceability.count_traced). "_fr_tagged" = back-compat.
    events_fr_tagged: int = 0
    # Test health (latest *full* suite, not the last event)
    latest_full_suite_passed: int | None = None
    latest_full_suite_total: int | None = None
    latest_full_suite_date: str = ""
    # Diff-coverage (% of the CHANGED lines vs merge-base that tests execute),
    # PR-local. None → not measurable → NO effect on Test-Health. This is the
    # repo-agnostic default: the generic grader supplies nothing, so an arbitrary
    # repo's grade is unchanged; only the monorepo compliance adapter populates
    # it from the gitignored transient (diff-coverage roadmap Phase 3 — below the
    # threshold it moderates Test-Health with a WARN + a non-collapsing penalty).
    diff_coverage_percent: float | None = None
    # Change → commit/ADR/test provenance
    events_with_provenance: int = 0
    # Whether change-traceability provenance is TRUSTWORTHY here (dim 3 gate).
    # Default True: every authoritative caller (the dashboard adapter, the engine
    # tests) populates events_with_provenance from real records — an ADR/commit/test
    # link, or the network PR-association ratio. The cold-repo grader sets this
    # False in local-only mode, where the ONLY signal is git-log `#N` references,
    # which ANTI-correlate with quality (a disciplined squash-merge repo leaves
    # reference-free subjects). False → dim 3 renders n/a ("needs --allow-network"),
    # mirroring how test-health/security degrade to n/a without a trustworthy signal
    # instead of scoring a misleading proxy.
    change_traceability_measurable: bool = True
    # Change reconciliation (BP-2 — behavior-affecting impact persisted)
    reconciliation_measurable: bool = False
    frs_behavior_touched: int = 0
    frs_unreconciled: int = 0
    # Security (None → no trustworthy local signal; see AR-10 CI ingest)
    security_measurable: bool = False
    security_open_high_critical: int | None = None
    # Size / maintainability (net ratchet growth; None → no baseline)
    bloat_ratchet_delta: int | None = None
    # Cold-repo static size proxy — fraction of source files over the size
    # threshold [0, 1]. Scored (dim 6) ONLY when ``bloat_ratchet_delta is None``
    # (additive, G2 — the dashboard's ratchet baseline path is untouched). None →
    # not measured. Kept a distinct field so the honest "N/M files over threshold"
    # detail is never smuggled into the ratchet-delta field.
    oversize_file_ratio: float | None = None
    # Dependency hygiene
    deps_total: int = 0
    deps_unknown_license: int = 0
    deps_copyleft: int = 0
    # Control pillars this repo is configured to measure. A pillar named here
    # whose score is None (n/a) is a *dark control* → the verdict is capped below
    # A and flagged "verification incomplete". Empty default → pure-scorer
    # back-compat (no expectation, no cap).
    expected_dimensions: tuple[str, ...] = ()
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

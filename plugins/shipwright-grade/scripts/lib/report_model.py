"""report_model — the typed report view-model (NOT markdown-as-IR).

A dataclass graph carrying the grade + per-dimension result + a **provenance
object** per dimension (source, mode, freshness, sampled/truncated flags,
disabled enrichments). Terminal / markdown (G1) and HTML (G3) render FROM this;
no renderer parses another renderer's text (GPT #11/#18).

n/a semantics (GPT #12): a dimension with ``score is None`` renders **N/A**
(never ``0/15``), is excluded from the score denominator (the engine already
does this), is listed under *controls Shipwright would light up*, and is never
coerced to a failing 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Per-dimension provenance metadata for the heuristic (cold-repo) grade in G1.
# ``disabled`` names the enrichments that WOULD light the dimension once wired.
_DIM_META: dict[str, dict[str, Any]] = {
    "requirement_traceability": {
        "source": "route/feature inference + git-log classification (heuristic)",
        "disabled": (),
    },
    "test_health": {
        "source": "static test inventory — present, not executed",
        "disabled": ("ci-junit-pass-ratio", "scorecard-check-runs"),
    },
    "change_traceability": {
        "source": "git-log PR/issue links (heuristic)",
        "disabled": ("ci-run-per-sha",),
    },
    "change_reconciliation": {
        "source": "Shipwright-only: per-change behaviour re-verification (BP-2)",
        "disabled": ("behavior-impact-ledger",),
    },
    "security": {
        "source": "deferred to G2: code-scanning SARIF / local scan",
        "disabled": ("code-scanning-sarif", "local-scan"),
    },
    "maintainability": {
        "source": "deferred to G2: oversize-file ratio",
        "disabled": ("oversize-file-ratio",),
    },
    "dependency_hygiene": {
        "source": "deferred to G2: lockfile → SBOM licenses",
        "disabled": ("lockfile-sbom",),
    },
}

_GIT_DERIVED = frozenset({"requirement_traceability", "change_traceability"})

HONEST_CEILING_NOTE = (
    "Heuristic estimate from the outside — it inspects history and structure, "
    "it does not verify behaviour. A cold-repo grade cannot certify correctness."
)


@dataclass(frozen=True)
class DimensionProvenance:
    source: str
    mode: str            # "heuristic" | "authoritative" | "unavailable"
    freshness: str       # short head sha, or "n/a"
    sampled: bool
    truncated: bool
    disabled_enrichments: tuple[str, ...]


@dataclass(frozen=True)
class DimensionView:
    key: str
    label: str
    weight: float
    score: float | None
    status: str          # "ok" | "gap" | "n/a"
    anchor: str
    detail: str
    provenance: DimensionProvenance
    would_light_up: bool


@dataclass(frozen=True)
class ReportModel:
    target_display: str
    grade: str
    score: float | None
    gradeable: bool
    verdict: str
    band_label: str
    mode: str
    routing_state: str
    routing_reason: str
    verified_from: str
    dimensions: tuple[DimensionView, ...]
    reasons: tuple[str, ...]
    measurable_count: int
    na_count: int
    controls_shipwright_would_light: tuple[str, ...]
    honest_ceiling_note: str
    static_test_inventory: str


def _provenance(
    key: str, *, score: float | None, effective_mode: str,
    freshness: str, events_truncated: bool, features_truncated: bool,
) -> DimensionProvenance:
    meta = _DIM_META.get(key, {"source": "unknown", "disabled": ()})
    mode = "unavailable" if score is None else effective_mode
    # Requirement-traceability samples when the repo exceeds the detector caps
    # (order-dependent feature truncation); labelled honestly rather than hidden.
    sampled = features_truncated and key == "requirement_traceability"
    truncated = (events_truncated and key in _GIT_DERIVED) or sampled
    return DimensionProvenance(
        source=str(meta["source"]),
        mode=mode,
        freshness=freshness if score is not None else "n/a",
        sampled=sampled,
        truncated=truncated,
        disabled_enrichments=tuple(meta["disabled"]),
    )


def build_report_model(
    *,
    grade_report: Any,
    routing: Any,
    target_display: str,
    head_sha: str,
    events_truncated: bool,
    features_truncated: bool = False,
    detail_overrides: dict[str, str] | None = None,
    static_test_inventory: str = "",
) -> ReportModel:
    """Assemble a :class:`ReportModel` from the engine report + provenance."""
    detail_overrides = detail_overrides or {}
    freshness = head_sha[:12] if head_sha else "n/a"

    views: list[DimensionView] = []
    na_labels: list[str] = []
    for dim in grade_report.dimensions:
        detail = detail_overrides.get(dim.key, dim.detail)
        prov = _provenance(
            dim.key, score=dim.score, effective_mode=routing.effective_mode,
            freshness=freshness, events_truncated=events_truncated,
            features_truncated=features_truncated,
        )
        would_light = dim.score is None
        if would_light:
            na_labels.append(dim.label)
        views.append(DimensionView(
            key=dim.key, label=dim.label, weight=dim.weight, score=dim.score,
            status=dim.status, anchor=dim.anchor, detail=detail,
            provenance=prov, would_light_up=would_light,
        ))

    measurable = sum(1 for d in views if d.score is not None)
    na = sum(1 for d in views if d.score is None)

    return ReportModel(
        target_display=target_display,
        grade=grade_report.grade,
        score=grade_report.score,
        gradeable=grade_report.gradeable,
        verdict=grade_report.verdict,
        band_label=grade_report.band_label,
        mode=routing.effective_mode,
        routing_state=routing.state,
        routing_reason=routing.reason,
        verified_from=grade_report.verified_from,
        dimensions=tuple(views),
        reasons=tuple(grade_report.reasons),
        measurable_count=measurable,
        na_count=na,
        controls_shipwright_would_light=tuple(na_labels),
        honest_ceiling_note=HONEST_CEILING_NOTE,
        static_test_inventory=static_test_inventory,
    )

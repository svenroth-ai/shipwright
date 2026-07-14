"""report_model — the typed report view-model (NOT markdown-as-IR).

A dataclass graph carrying the grade + per-dimension result + a **provenance
object** per dimension (source, mode, freshness, sampled/truncated flags,
disabled enrichments). Terminal / markdown (G1) and HTML (G3) render FROM this;
no renderer parses another renderer's text (GPT #11/#18).

n/a semantics (GPT #12): a dimension with ``score is None`` renders **N/A**
(never ``0/15``), is excluded from the score denominator (the engine already
does this), is listed under *controls Shipwright would light up*, and is never
coerced to a failing 0.

⚠️ **CROSS-REPO CONTRACT — an external consumer renders this model.** The Command
Center WebUI (github.com/svenroth-ai/shipwright-webui) renders the ``ReportModel``
graph *field-for-field* on its "Grade your repo" screen, so that screen and the
downloadable HTML report cannot tell different stories. It reaches the WebUI as
``grade.py --format json`` (literally ``json.dumps(dataclasses.asdict(model))``),
so **every field here is on the wire**.

A field renamed or dropped here does NOT fail loudly over there — it renders a
half-empty card, or a plausible-but-wrong one. Before you change this shape, read
the "Cross-repo contract" section of ``skills/grade/SKILL.md``. The gate in
``tests/test_report_model_contract.py`` will stop you and tell you what to do.
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
        "source": "Shipwright-only: per-change behaviour re-verification",
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

# The version of the wire shape this model serializes to (see the module docstring).
# MAJOR = breaking for the consumer (a field removed, renamed or retyped) — the WebUI
# must REFUSE to render an unrecognised major rather than half-render it. MINOR =
# additive (a new field) — the WebUI keeps rendering and ignores what it doesn't know,
# so an addition must NOT force a WebUI release, or people would stop bumping at all.
#
# You are not expected to remember to bump this: tests/test_report_model_contract.py
# diffs the live payload against the contract fixture as of origin/main, derives the
# bump that diff obliges, and fails until it has been performed.
SCHEMA_VERSION = "1.0"

# The closed value domain of DimensionView.status. The WebUI BRANCHES on these: "n/a"
# draws as absent evidence (a dashed track), never as a zero-score bar. A 4th value
# would break its rendering while leaving every field name and type untouched — the
# one break the structural gate cannot see — so it is pinned separately.
STATUS_VOCABULARY = ("gap", "n/a", "ok")

# The honest-ceiling note is mode-dependent: an authoritative grade is NOT an
# "estimate from the outside" — it is computed from the repo's own Shipwright
# records — so claiming it is would itself be dishonest (the exact over-claim the
# ceiling exists to prevent).
HONEST_CEILING_NOTE = (  # heuristic / cold-repo projection
    "Heuristic estimate from the outside — it inspects history and structure, "
    "it does not verify behaviour. A cold-repo grade cannot certify correctness."
)
AUTHORITATIVE_CEILING_NOTE = (
    "Computed from this repo's own Shipwright records (event log + RTM) — the same "
    "rubric the dashboard and certification use. A grade measures control "
    "discipline, not behaviour-correctness; it is not a security audit or a guarantee."
)


def ceiling_note_for(effective_mode: str) -> str:
    """The honest-ceiling note matching the grade's mode (authoritative vs cold)."""
    if effective_mode == "authoritative":
        return AUTHORITATIVE_CEILING_NOTE
    return HONEST_CEILING_NOTE


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
    # Network provenance (G2) — exactly what left the machine (§14 D).
    network_enabled: bool = False
    network_note: str = ""
    network_enrichments: tuple[str, ...] = ()
    # Wire-shape version for the external consumer. Last, and defaulted, so every
    # existing constructor keeps working (a defaulted field may not precede a
    # non-defaulted one) and it lands in asdict() → --format json for free.
    schema_version: str = SCHEMA_VERSION


def _provenance(
    key: str, *, score: float | None, effective_mode: str,
    freshness: str, events_truncated: bool, features_truncated: bool,
    override: dict | None = None,
) -> DimensionProvenance:
    meta = _DIM_META.get(key, {"source": "unknown", "disabled": ()})
    source = str(meta["source"])
    disabled = tuple(meta["disabled"])
    # A dimension lit/moved by a G2 signal supplies its real source + the
    # enrichments still dark, replacing the static G1 placeholder.
    if override:
        if override.get("source"):
            source = str(override["source"])
        if "disabled" in override:
            disabled = tuple(override["disabled"])
    mode = "unavailable" if score is None else effective_mode
    # Requirement-traceability samples when the repo exceeds the detector caps
    # (order-dependent feature truncation); labelled honestly rather than hidden.
    sampled = features_truncated and key == "requirement_traceability"
    truncated = (events_truncated and key in _GIT_DERIVED) or sampled
    return DimensionProvenance(
        source=source,
        mode=mode,
        freshness=freshness if score is not None else "n/a",
        sampled=sampled,
        truncated=truncated,
        disabled_enrichments=disabled,
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
    provenance_overrides: dict[str, dict] | None = None,
    network_enabled: bool = False,
    network_note: str = "",
    network_enrichments: tuple[str, ...] = (),
) -> ReportModel:
    """Assemble a :class:`ReportModel` from the engine report + provenance."""
    detail_overrides = detail_overrides or {}
    provenance_overrides = provenance_overrides or {}
    freshness = head_sha[:12] if head_sha else "n/a"

    views: list[DimensionView] = []
    na_labels: list[str] = []
    for dim in grade_report.dimensions:
        detail = detail_overrides.get(dim.key, dim.detail)
        prov = _provenance(
            dim.key, score=dim.score, effective_mode=routing.effective_mode,
            freshness=freshness, events_truncated=events_truncated,
            features_truncated=features_truncated,
            override=provenance_overrides.get(dim.key),
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

    # Consistency: the engine builds its top-reasons from its own dimension
    # details, so a reason that quotes a detail we overrode would disagree with
    # the dimension table. Rewrite those reasons to the overridden phrasing.
    fixups = {
        f"{d.label}: {d.detail}": f"{d.label}: {detail_overrides[d.key]}"
        for d in grade_report.dimensions if d.key in detail_overrides
    }
    reasons = tuple(fixups.get(r, r) for r in grade_report.reasons)

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
        reasons=reasons,
        measurable_count=measurable,
        na_count=na,
        controls_shipwright_would_light=tuple(na_labels),
        honest_ceiling_note=ceiling_note_for(routing.effective_mode),
        static_test_inventory=static_test_inventory,
        network_enabled=network_enabled,
        network_note=network_note,
        network_enrichments=tuple(network_enrichments),
    )

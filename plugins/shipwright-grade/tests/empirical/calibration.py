"""calibration — the OFFLINE half of the empirical suite.

Re-grade a recorded fixture (projected ``GradeInputs`` + report-extras) with the
shared engine and assert **bands + relative ordering** — never exact scores. This
runs with NO network: the engine (``compute_grade``) executes on every replay, so
the offline suite still catches rubric regressions (plan §14). A drift in an exact
score is a review signal (a fixture JSON diff on ``--refresh``), not a red build.

The fixture schema is versioned: a mismatch is a hard, actionable error
("refresh required") rather than a silent mis-render.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine_bridge import load_engine
from report_model import ReportModel, build_report_model

#: Bump when the recorded fixture shape changes incompatibly (forces a refresh).
SCHEMA_VERSION = 1

#: A→F rank (0 = best). Used for band-set parsing and ordering.
BAND_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}

#: Calibration tiers, best → worst. Ordering asserts min(higher) > max(lower).
TIERS = ("exemplary", "average", "poor")


class FixtureVersionError(RuntimeError):
    """A cached fixture predates the current schema — re-record with --refresh."""


class OrderingError(AssertionError):
    """The cross-tier grade ordering (exemplary > average > poor) is violated."""


@dataclass(frozen=True)
class _RoutingShim:
    """The three ``build_report_model`` reads off a RoutingDecision, rehydrated."""

    effective_mode: str
    state: str
    reason: str


def parse_band_set(spec: str | None) -> frozenset[str]:
    """Parse an ``expected_band`` spec into the set of accepted bands.

    ``"A"`` → ``{A}``; ``"A/B"`` / ``"A-B"`` / ``"A B"`` → ``{A, B}`` (calibration
    tolerance — assert the band lands in a range, never an exact score). An empty
    / falsy spec (edge-case entries) → the empty set (no band assertion).
    """
    if not spec:
        return frozenset()
    tokens = [t.strip().upper() for t in spec.replace("/", " ").replace("-", " ").replace(",", " ").split()]
    return frozenset(t for t in tokens if t in BAND_ORDER)


def grade_from_fixture(fixture: dict[str, Any]) -> ReportModel:
    """Re-grade a recorded fixture OFFLINE → the identical ReportModel.

    Runs the shared engine on the cached ``GradeInputs`` and rebuilds the view
    model from the cached ``report_extras`` — no network, no repo checkout.
    """
    version = fixture.get("schema_version")
    if version != SCHEMA_VERSION:
        raise FixtureVersionError(
            f"fixture schema v{version} != v{SCHEMA_VERSION} — re-record with "
            f"`run_empirical.py --refresh` (repo {fixture.get('repo')!r})")

    engine = load_engine()
    gi = dict(fixture["grade_inputs"])
    # JSON turns the ``expected_dimensions`` tuple into a list; the engine field
    # is a tuple. Every other GradeInputs field is a flat primitive (verified in
    # _grade_types.py), so this is the only coercion the round-trip needs.
    gi["expected_dimensions"] = tuple(gi.get("expected_dimensions") or ())
    report = engine.compute_grade(engine.GradeInputs(**gi))

    ex = fixture["report_extras"]
    routing = _RoutingShim(**ex["routing"])
    return build_report_model(
        grade_report=report,
        routing=routing,
        target_display=ex["target_display"],
        head_sha=ex["head_sha"],
        events_truncated=ex["events_truncated"],
        features_truncated=ex.get("features_truncated", False),
        detail_overrides=ex.get("detail_overrides") or {},
        static_test_inventory=ex.get("static_test_inventory", ""),
        provenance_overrides=ex.get("provenance_overrides") or {},
        network_enabled=ex.get("network_enabled", False),
        network_note=ex.get("network_note", ""),
        network_enrichments=tuple(ex.get("network_enrichments") or ()),
    )


def assert_band(name: str, model: ReportModel, expected_spec: str | None) -> None:
    """Assert ``model``'s band is within the accepted set. No-op for edge cases
    (empty spec) — those only assert robustness (graded, no crash)."""
    accepted = parse_band_set(expected_spec)
    if not accepted:
        assert model.gradeable, f"{name}: expected a gradeable result, got '?'"
        return
    assert model.grade in accepted, (
        f"{name}: graded {model.grade} (score {model.score}); "
        f"expected band in {sorted(accepted)}")


@dataclass(frozen=True)
class CalibrationResult:
    name: str
    tier: str | None
    band: str
    score: float | None
    expected_band: str | None


def _tier_of(tags: list[str] | tuple[str, ...] | None) -> str | None:
    for tier in TIERS:
        if tags and tier in tags:
            return tier
    return None


def result_for(name: str, model: ReportModel, entry: dict[str, Any]) -> CalibrationResult:
    return CalibrationResult(
        name=name,
        tier=_tier_of(entry.get("tags")),
        band=model.grade,
        score=model.score,
        expected_band=entry.get("expected_band"),
    )


def assert_ordering(results: list[CalibrationResult]) -> None:
    """Assert exemplary > average > poor across the calibration tiers.

    Strict ``>`` is enforced ONLY *between* adjacent tiers (a rubric regression
    that flattens the range is what this catches); WITHIN a tier only band
    membership is asserted (elsewhere), so a numeric tie never flakes the gate.
    Tiers with no non-n/a score are skipped.
    """
    scored: dict[str, list[float]] = {t: [] for t in TIERS}
    for r in results:
        if r.tier in scored and r.score is not None:
            scored[r.tier].append(r.score)

    present = [(t, scored[t]) for t in TIERS if scored[t]]
    for (higher_tier, higher), (lower_tier, lower) in zip(present, present[1:]):
        if min(higher) <= max(lower):
            raise OrderingError(
                f"ordering violated: {higher_tier} (min {min(higher):.1f}) must "
                f"outscore {lower_tier} (max {max(lower):.1f})")

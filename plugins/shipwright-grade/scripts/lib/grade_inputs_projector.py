"""grade_inputs_projector — map a RepoContext onto GradeInputs, then grade.

This is the cold-repo → ``GradeInputs`` projection. It reuses
``compute_grade`` **UNCHANGED** (loaded via ``engine_bridge``): the grader's
whole value is that a cold-repo grade equals the dashboard grade by
construction.

Dimensions (heuristic, best-available):
- **requirement traceability** / **change traceability** — from git history (G1).
- **maintainability** — static oversize-file ratio (local; G2 additive engine field).
- **dependency hygiene** — lockfile → SBOM license resolution (local; G2).
- **test health** — layered CI-JUnit / Scorecard-check / static-inventory tiers (G2).
- **security** — GitHub code-scanning SARIF (G2), network-only.

The G2 signals come from :mod:`signal_bundle`; the network-only dims (test-health
tiers 1-2, security) light only when ``--allow-network`` resolves an enrichable
target (see :mod:`network_policy`). **change reconciliation** stays n/a — the
Shipwright-only dimension. ``expected_dimensions`` is empty so every n/a dimension
is a "control Shipwright would light up", never a dark-control cap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from authoritative import try_authoritative_grade
from engine_bridge import Engine, load_engine
from gh_bridge import GhRunner, run_gh
from network_policy import NetworkPolicy
from report_model import ReportModel, build_report_model
from repo_context import RepoContext
from routing import decide_routing
from signal_bundle import SignalBundle, compute_signals

# Bound the coverage scan so a hostile/huge repo can't blow the budget.
_MAX_TEST_FILES_SCANNED = 200
_COVERAGE_READ_BYTES = 50_000


@dataclass(frozen=True)
class ProjectionExtras:
    static_test_inventory: str
    detail_overrides: dict[str, str]


@dataclass(frozen=True)
class GradeComputation:
    """A grade result plus the pre-engine intermediates the empirical harness
    (G5) records for offline record/replay.

    ``grade_inputs`` / ``report_extras`` are ``None`` for an **authoritative**
    grade (built from the target's own records, not a projected ``GradeInputs``);
    the empirical set is external OSS, so it is always heuristic and both are
    populated. ``report_extras`` holds exactly the ``build_report_model``
    side-inputs, so a cached ``GradeInputs`` re-grades to the identical model
    offline.
    """

    report: ReportModel
    grade_inputs: Any | None
    report_extras: dict[str, Any] | None


def _frameworks(context: RepoContext) -> list[str]:
    seen: list[str] = []
    for layer in ("unit", "integration", "e2e", "db"):
        info = context.test_frameworks.get(layer)
        if isinstance(info, dict):
            name = info.get("framework")
            if name and name not in seen:
                seen.append(str(name))
    return seen


def _static_inventory_line(context: RepoContext) -> str:
    frameworks = _frameworks(context)
    count = context.test_file_count
    if count == 0 and not frameworks:
        return ""
    fw = ", ".join(frameworks) if frameworks else "unknown framework"
    plural = "s" if count != 1 else ""
    line = f"{count} test file{plural} across {len(frameworks) or 1} framework"
    line += f" ({fw}) — present, not executed"
    if context.has_ci:
        line += "; CI workflow present"
    return line


def _feature_covered(feature: dict[str, Any], test_texts: list[str]) -> bool:
    """A feature is 'covered' iff a test references its **route-specific** signal.

    Uses the route (and its distinctive static segments), NOT the source module
    path: many features share one source file, so a module-path match would mark
    every route in that file covered off a single import — systematically
    over-counting coverage (the honesty-inflating failure mode). A feature with
    no distinctive route token is treated as not covered (conservative).
    """
    route = str(feature.get("route", "")).strip("/")
    needles: list[str] = []
    if route:
        needles.append(route)
        for seg in route.split("/"):
            if seg and seg[0] not in "{[:<*" and len(seg) >= 4:
                needles.append(seg)  # a static, discriminating path segment
    needles = [n for n in dict.fromkeys(needles) if len(n) >= 4]
    if not needles:
        return False
    return any(any(n in text for n in needles) for text in test_texts)


def _count_covered(context: RepoContext) -> int:
    if not context.features:
        return 0
    scanned = context.test_files[:_MAX_TEST_FILES_SCANNED]
    test_texts = [context.read_text(f, max_bytes=_COVERAGE_READ_BYTES) for f in scanned]
    return sum(1 for f in context.features if _feature_covered(f, test_texts))


def _local_only_policy() -> NetworkPolicy:
    return NetworkPolicy(
        enabled=False, requested=False, owner=None, repo=None,
        visibility="local-only", note="local-only (default)")


def project_inputs(
    context: RepoContext, engine: Engine, bundle: SignalBundle,
    *, network_enabled: bool = False,
) -> tuple[Any, ProjectionExtras]:
    """Map ``context`` + the G2 ``bundle`` onto a ``GradeInputs`` value + extras."""
    events = context.events
    events_total = len(events)
    fr_tagged = sum(1 for e in events if e.is_traced)
    with_provenance = sum(1 for e in events if e.has_provenance)

    frs_total = len(context.features)
    frs_covered = _count_covered(context)

    head = context.head_sha[:12] if context.head_sha else "unknown"
    mode = "network-enriched" if network_enabled else "local-only"
    verified_from = f"shipwright-grade heuristic @ {head} ({mode})"

    inputs = engine.GradeInputs(
        frs_total=frs_total,
        frs_covered=frs_covered,
        events_total=events_total,
        events_fr_tagged=fr_tagged,
        events_with_provenance=with_provenance,
        # Reconciliation stays n/a (the Shipwright-only dimension); the security,
        # deps, maintainability + test-health dims are lit by the G2 bundle where
        # measurable, else keep their honest n/a engine defaults.
        expected_dimensions=(),
        verified_from=verified_from,
        **bundle.grade_input_kwargs(),
    )

    inventory = _static_inventory_line(context)
    overrides: dict[str, str] = {}
    # The inventory line already reads "… — present, not executed"; use it as-is
    # for the n/a test-health detail (a scored tier overrides it below).
    overrides["test_health"] = inventory or "no test suite detected"
    # The bundle's honest per-dimension details win (a scored test-health tier
    # labels itself; security/deps/size carry their real signal state).
    overrides.update(bundle.detail_overrides())
    return inputs, ProjectionExtras(static_test_inventory=inventory,
                                    detail_overrides=overrides)


def grade_context(
    context: RepoContext,
    *,
    policy: NetworkPolicy | None = None,
    gh: GhRunner | None = None,
) -> ReportModel:
    """Full pipeline: signals → project → grade (engine unchanged) → view-model.

    ``policy`` defaults to **local-only** (no network); ``grade.py`` passes a
    resolved policy when ``--allow-network`` is set. Thin wrapper over
    :func:`grade_context_captured` — the public return is the ``.report`` field,
    byte-identical to the pre-G5 behaviour (see ``test_projector_capture``).
    """
    return grade_context_captured(context, policy=policy, gh=gh).report


def grade_context_captured(
    context: RepoContext,
    *,
    policy: NetworkPolicy | None = None,
    gh: GhRunner | None = None,
) -> GradeComputation:
    """Grade ``context`` and also expose the pre-engine ``GradeInputs`` + the
    ``build_report_model`` side-inputs, so the empirical harness (G5) can record
    a repo's projection once and re-grade it **offline** on replay.

    An authoritative grade returns ``grade_inputs=None`` / ``report_extras=None``
    (it is not a projected ``GradeInputs``); the recorder rejects that case
    explicitly rather than caching a divergent shape.
    """
    engine = load_engine()
    policy = policy or _local_only_policy()
    gh = gh or run_gh

    # Authoritative-vs-heuristic routing (plan §4 C-R4). A healthy, current
    # `.shipwright/` event log + RTM is graded from the target's OWN records; any
    # corrupt / partial / stale / degenerate case falls back to the heuristic
    # projection below, labelled. ``head_sha`` enables the staleness check.
    routing = decide_routing(context.root, head_sha=context.head_sha)
    if routing.detected_mode == "authoritative":
        authoritative = try_authoritative_grade(context, engine, routing)
        if authoritative is not None:
            return GradeComputation(
                report=authoritative, grade_inputs=None, report_extras=None)

    bundle = compute_signals(context, policy, gh)
    inputs, extras = project_inputs(
        context, engine, bundle, network_enabled=policy.enabled)
    report = engine.compute_grade(inputs)
    report_extras: dict[str, Any] = {
        "target_display": context.root.name or "repository",
        "head_sha": context.head_sha or "",
        "events_truncated": context.events_truncated,
        "features_truncated": context.features_truncated,
        "detail_overrides": extras.detail_overrides,
        "static_test_inventory": extras.static_test_inventory,
        "provenance_overrides": bundle.provenance(),
        "network_enabled": policy.enabled,
        "network_note": policy.note,
        "network_enrichments": list(policy.enrichments),
        "routing": {
            "effective_mode": routing.effective_mode,
            "state": routing.state,
            "reason": routing.reason,
        },
    }
    model = build_report_model(
        grade_report=report,
        routing=routing,
        target_display=report_extras["target_display"],
        head_sha=report_extras["head_sha"],
        events_truncated=report_extras["events_truncated"],
        features_truncated=report_extras["features_truncated"],
        detail_overrides=report_extras["detail_overrides"],
        static_test_inventory=report_extras["static_test_inventory"],
        provenance_overrides=report_extras["provenance_overrides"],
        network_enabled=report_extras["network_enabled"],
        network_note=report_extras["network_note"],
        network_enrichments=tuple(report_extras["network_enrichments"]),
    )
    return GradeComputation(
        report=model, grade_inputs=inputs, report_extras=report_extras)

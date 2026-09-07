"""Pure evaluator for the binding-completeness F11 gate (P3.3, SPEC §5 S3/Track V).

Split from ``_layer_coverage_core`` (300-LOC cap) the moment this landed, same
precedent ``_layer_coverage_removal`` already set. Operates only on the two
*already-regenerated* base/head manifests (R3), like every gate in this family.

A behaviour-changed FR's declared binding (``required_layers``) must name at
least the HIGHEST layer this run's OWN evidence proves executed-passing: "the
binding must include the highest observable layer" (campaign SPEC, P3.3) — a
binding that names only unit tests is rejected once an executed-passing
integration/e2e test exists for the same requirement. A coarser binding than
the evidence supports understates what :func:`_layer_coverage_core.evaluate_cross_layer`
actually enforces going forward: the next regression at the higher, unbound
layer would not be required to stay green — a real gap in the "keep the spec
true as the code changes" promise the whole campaign exists to close (P3.6 is
the eventual AC-level keystone; this is the FR-level binding it depends on).
"""

from __future__ import annotations

from ._layer_coverage_core import (
    CrossLayerVerdict,
    LayerGap,
    _active_nodes,
    behavior_changed_keys,
    collision_display_ids,
    criteria_changed_keys,
    route_gap_severity,
)

#: Rank of each canonical test layer, lowest to highest observable. Any layer name
#: outside this set (a legacy/free-form token in a hand-authored ``Layers`` cell)
#: ranks below every canonical layer (``-1``) — an unrecognised required layer must
#: never be credited with covering a real, higher, KNOWN layer.
_LAYER_RANK = {"unit": 0, "integration": 1, "e2e": 2}


def _highest_ok_layer(coverage: dict) -> str | None:
    """The highest-ranked layer in ``coverage`` reporting an executed-passing test
    (``"ok"``), or ``None`` when no layer does. ``coverage`` keys are always a
    subset of ``_LAYER_ORDER`` (``_test_links_requirements.build_requirement_nodes``),
    so every candidate is a canonical, ranked layer.

    Eligibility is not invented here: ``"ok"`` is exactly
    ``_test_links_requirements._cov_status``'s verdict — a tagged link that is
    BOTH ``enabled`` and ``executed=pass`` in THIS run's provenance-verified
    evidence (:mod:`_layer_coverage_core`'s module docstring). This function
    reuses that single existing eligibility contract rather than defining a
    second one; a failed, skipped, or unexecuted test at a layer never counts,
    the same as it never counts for :func:`_layer_coverage_core.evaluate_cross_layer`.

    **Fail-OPEN, not fail-closed, for an unrecognised label reaching the CALLER's
    comparison** (external code review, P3.3, glm): this function itself never
    credits an unrecognised label over a canonical one (rank ``-1`` always loses
    to rank ``>=0``, pinned by
    ``test_highest_ok_layer_ranks_an_unrecognised_layer_label_below_every_canonical_one``).
    But when it is the ONLY key present, it is returned verbatim, and the caller's
    ``_LAYER_RANK.get(highest_ok, -1) <= max_required_rank`` then reads ``-1`` on
    BOTH sides for an empty ``required_layers`` — ``-1 <= -1`` is true, so no gap
    is raised. This is intentionally the same "nothing to judge yet" behaviour an
    empty/all-MISSING ``coverage`` already gets (see
    ``test_no_gap_when_no_layer_has_executed_passing_evidence``), not a second,
    silently-different fail-closed rule — and it is unreachable from a real
    manifest today, since ``coverage`` keys are canonical by construction.
    """
    ok_layers = [layer for layer, status in coverage.items() if status == "ok"]
    if not ok_layers:
        return None
    return max(ok_layers, key=lambda layer: _LAYER_RANK.get(layer, -1))


def evaluate_binding_completeness(
    base: dict, head: dict, ac_changed_ids: set[str] | None = None,
) -> CrossLayerVerdict:
    """Each behaviour-changed FR's binding must include the highest executed-passing
    layer this run's evidence shows (P3.3).

    Reuses :func:`behavior_changed_keys` / :func:`criteria_changed_keys` — the
    SAME behaviour-change signal :func:`_layer_coverage_core.evaluate_cross_layer`
    uses — so the two gates can never disagree about WHICH FRs are in scope this
    run, only about what each one demands of them. Severity routing calls the
    SAME :func:`_layer_coverage_core.route_gap_severity` ``evaluate_cross_layer``
    calls (external plan review, P3.3: two copies of one routing rule drift the
    first time either changes) — unknown/explicit provenance is HARD, a KNOWN
    legacy source is ADVISORY (the pre-rollout valve — today's entire manifest is
    ``inferred_legacy``), and a collision display id is ADVISORY regardless
    (fail-closed vs a false-red on a structurally-ambiguous id).

    No gap when ``required_layers`` already names a layer at least as high as
    the highest executed-passing one, or when the node has no executed-passing
    layer at all — this function only fires once the run's OWN evidence outruns
    what the binding declares, never on a requirement with no evidence to judge.
    """
    row_changed = behavior_changed_keys(base, head)
    ac_changed = criteria_changed_keys(head, ac_changed_ids)
    changed = row_changed + [k for k in ac_changed if k not in row_changed]
    verdict = CrossLayerVerdict(changed_keys=changed)
    if not changed:
        return verdict

    head_active = _active_nodes(head)
    collisions = collision_display_ids(head)
    for key in changed:
        node = head_active.get(key)
        if node is None:
            continue
        highest_ok = _highest_ok_layer(node.get("coverage") or {})
        if highest_ok is None:
            continue
        required = node.get("required_layers") or []
        max_required_rank = max((_LAYER_RANK.get(r, -1) for r in required), default=-1)
        if _LAYER_RANK.get(highest_ok, -1) <= max_required_rank:
            continue  # binding already names a layer at least as high as the evidence
        disp = node.get("id")
        source = node.get("required_layers_source") or "__missing__"
        priority = node.get("priority", "Must")
        ambiguous = disp in collisions
        gap = LayerGap(
            disp, key, highest_ok, priority, source,
            "ambiguous_fanout" if ambiguous else "BINDING_INCOMPLETE",
        )
        getattr(verdict, route_gap_severity(ambiguous=ambiguous, source=source)).append(gap)
    return verdict


__all__ = ["evaluate_binding_completeness"]

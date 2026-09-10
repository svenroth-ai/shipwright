"""D10's "highest layer mandatory", at AC granularity — THE KEYSTONE GATE (P3.6).

Own module so :mod:`_keystone_core` stays under the source-size limit and so the
one thing here that is easy to get wrong has a single obvious subject.

**What is reused vs what is new.** Reused from P3.3: ``_LAYER_RANK`` (the
canonical layer ordering) and ``route_gap_severity`` (the shared severity rule
P3.3's own external plan review insisted on, so two gates cannot drift on how a
gap is routed). **NOT reused: ``evaluate_binding_completeness``** — it tests the
INVERSE direction, firing when a run's observed evidence OUTRANKS the declared
``required_layers``, while this needs an AC's binding covering LESS than its FR
requires. Reaching for it would implement the wrong predicate. The comparison
below is this gate's own; a drift test asserts both reuses are identity and that
the wrong function is never referenced.
"""

from __future__ import annotations

from ._keystone_finding import LAYER_GAP, Finding
from ._layer_coverage_binding import _LAYER_RANK
from ._layer_coverage_core import _active_nodes, collision_display_ids, route_gap_severity

__all__ = ["_LAYER_RANK", "layer_gap", "route_gap_severity"]


def _fr_node(manifest: dict, fr_id: str) -> dict | None:
    for node in _active_nodes(manifest).values():
        if node.get("id") == fr_id:
            return node
    return None


def layer_gap(head: dict, fr_id: str, ac_id: str, links: list[dict]) -> Finding | None:
    """"Highest layer mandatory" (D10) at AC granularity.

    Reused from P3.3: ``_LAYER_RANK`` (the canonical ordering) and
    ``route_gap_severity`` (the shared severity rule). NOT reused:
    ``evaluate_binding_completeness`` -- it tests the INVERSE direction (observed
    evidence OUTRANKING the declared ``required_layers``), while this needs an
    AC's binding covering LESS than its FR requires. Reaching for it would
    implement the wrong predicate; the comparison below is this gate's own.

    Routing is the family's, unchanged: ``explicit`` (or unknown) provenance is
    HARD, a KNOWN legacy source is ADVISORY (the pre-rollout valve -- every FR
    here is ``inferred_legacy`` today, so this arm stays advisory until P3.5
    promotes an FR), and a collision display id is ADVISORY regardless.
    """
    node = _fr_node(head, fr_id)
    if node is None:
        return None
    required = [r for r in (node.get("required_layers") or []) if r in _LAYER_RANK]
    if not required:
        return None
    max_required = max(_LAYER_RANK[r] for r in required)
    covered = {link.get("layer") for link in links}
    max_covered = max((_LAYER_RANK.get(x, -1) for x in covered), default=-1)
    if max_covered >= max_required:
        return None
    highest_required = max(required, key=lambda r: _LAYER_RANK[r])
    source = node.get("required_layers_source") or "__missing__"
    ambiguous = fr_id in collision_display_ids(head)
    return Finding(
        LAYER_GAP, fr_id, ac_id,
        f"changed AC is bound only at {sorted(x for x in covered if x)!r} but {fr_id} requires "
        f"{highest_required!r} -- the highest required layer is mandatory (D10). "
        f"(required_layers_source={source})",
        route_gap_severity(ambiguous=ambiguous, source=source),
    )

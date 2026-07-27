"""Pure evaluators for the two enforcing F11 traceability gates (Spec §11 R2/R3).

No git, no filesystem, no cross-plugin imports — every function here operates on the
two *already-regenerated* schema-v2 manifests (base + head) that
``_layer_coverage_regen`` builds from the base and head checkouts (R3: the committed
``test-traceability.json`` is never the enforcement source). Keeping the decision logic
pure makes both gates unit-testable against the P1 base/head fixtures without a git repo,
and keeps the false-green/false-red reasoning auditable in one place.

The two verdicts:

* :func:`evaluate_removal` — an FR that was ``active`` at base but is no longer active at
  head (moved into ``## Removed Requirements`` or deleted) must have every base-linked
  test deleted or retargeted to a *live* FR. A bare ``@FR`` tag removal (the test escapes
  into ``untagged_tests``) or a still-standing tag → dead FR is a HARD finding — that is
  the exact rot (a removed feature's E2E spec still green) the campaign exists to catch.
* :func:`evaluate_cross_layer` — an FR whose spec row changed between base and head (a
  behaviour-change signal from the spec/AC/FR delta, **not** source-file inference) must
  have an *executed-passing* tagged test at every ``required_layer`` (R1). A pure refactor
  produces an identical base/head spec → no changed FR → the gate does not fire.

Collision (un-namespaced tag fan-out) handling — carry-forward from TT2 doubt #3: a
display id shared across namespaces is AMBIGUOUS. Its coverage ``ok`` is never credited
(fail-closed vs false-green) AND its gap is never a HARD block (fail-closed vs a false-red
on a legitimately-covered collision FR). Both gates route collision cases to ADVISORY.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# required_layers provenance that keeps a gap ADVISORY (the pre-rollout legacy valve).
# Mirrors ``_group_d_traceability._LEGACY_SOURCES`` (SSoT is the D-layer detective; the
# set is trivial + pinned by ``test_layer_coverage`` so the two cannot silently diverge —
# a shared verifier must NOT cross-plugin-import the compliance audit module, ADR-044).
_LEGACY_SOURCES = frozenset({"inferred_legacy", "defaulted_legacy"})


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def _active_nodes(manifest: dict) -> dict[str, dict]:
    """Manifest key → node for every ``active`` requirement."""
    return {
        key: node
        for key, node in (manifest.get("requirements") or {}).items()
        if isinstance(node, dict) and node.get("status") == "active"
    }


def collision_display_ids(manifest: dict) -> set[str]:
    """Display ids shared by ≥2 requirement nodes across namespaces (any status).

    Inline copy of ``_group_d_manifest.collision_ids`` (a shared verifier cannot import
    the compliance plugin's audit lib, ADR-044). Counts BOTH active and removed
    occurrences: an id active in ns-A and removed in ns-B still fans a bare ``@FR`` tag
    onto A, so A's coverage may be credited by a tag that belongs to B — ambiguous.
    """
    seen: dict[str, int] = {}
    for node in (manifest.get("requirements") or {}).values():
        disp = node.get("id") if isinstance(node, dict) else None
        if disp is not None:
            seen[disp] = seen.get(disp, 0) + 1
    return {i for i, n in seen.items() if n > 1}


# The removal → orphan gate (``evaluate_removal`` + ``HeadIndex``) lives in
# ``_layer_coverage_removal`` (300-LOC split); it imports the two shared helpers above.


# ---------------------------------------------------------------------------
# Change → cross-layer gate
# ---------------------------------------------------------------------------


@dataclass
class LayerGap:
    display: str
    key: str
    layer: str
    priority: str
    source: str
    reason: str        # MISSING | ambiguous_fanout


@dataclass
class CrossLayerVerdict:
    changed_keys: list[str] = field(default_factory=list)
    hard: list[LayerGap] = field(default_factory=list)
    advisory: list[LayerGap] = field(default_factory=list)
    could_not_determine: bool = False

    @property
    def any_fail(self) -> bool:
        return bool(self.hard)


def _norm_title(node: dict) -> str:
    return " ".join(str(node.get("title") or "").split())


def behavior_changed_keys(base: dict, head: dict) -> list[str]:
    """Head active-FR keys whose spec row changed vs base (the behaviour-change signal).

    A key is behaviour-changed when it is NEW at head, or its title/required_layers
    differ from base. This is a real spec/FR-mapping delta (R2) recomputed from the two
    regenerated manifests — never source-file inference and never the self-reported
    event ``fr_impact`` (R3). A pure refactor leaves base==head specs → empty.
    """
    base_active = _active_nodes(base)
    changed: list[str] = []
    for key, hnode in _active_nodes(head).items():
        bnode = base_active.get(key)
        if bnode is None:
            changed.append(key)
        elif _norm_title(bnode) != _norm_title(hnode):
            changed.append(key)
        elif sorted(bnode.get("required_layers") or []) != sorted(hnode.get("required_layers") or []):
            changed.append(key)
    return changed


def criteria_changed_keys(head: dict, ac_changed_ids: set[str] | None) -> list[str]:
    """Head ACTIVE keys whose acceptance criteria changed between base and head.

    ``ac_changed_ids`` holds display ids (``FR-01.03``) computed by
    ``_layer_coverage_ac`` from the two spec checkouts. They are mapped onto
    manifest keys here, and filtered to ACTIVE nodes: a requirement moved to
    ``## Removed Requirements`` loses its section, which is the removal gate's
    business, not this one's. A collision display id maps to every key that
    carries it (fail-closed — collisions then route to ADVISORY as usual).
    """
    if not ac_changed_ids:
        return []
    return [
        key for key, node in _active_nodes(head).items()
        if node.get("id") in ac_changed_ids
    ]


def evaluate_cross_layer(
    base: dict, head: dict, ac_changed_ids: set[str] | None = None,
) -> CrossLayerVerdict:
    """Each behaviour-changed FR must be executed-passing at every required layer (R1).

    Severity routing mirrors ``D-layer`` exactly: an ``explicit`` (or unknown-provenance)
    required layer with no executed-passing test → HARD; a KNOWN legacy source → ADVISORY
    (the pre-rollout valve, so the gate is not a blanket-blocker on legacy FRs); a
    collision display id → ADVISORY regardless (its ``ok`` is never credited AND a HARD
    block would be a false-red).

    **Behaviour change is the union of two signals** (iterate-2026-07-27-name-the-blocker):
    the FR ROW changing (title / required_layers), and the requirement's own ACCEPTANCE
    CRITERIA changing. The row alone was not enough: ``shared/fr-authoring.md`` §3 makes
    FOLDING the common case — append a criterion to an existing requirement rather than
    mint a row — so a correctly folded change left the row identical and the gate saw
    nothing. The union also closes a quieter hole: ``could_not_determine`` is only reached
    when NO row changed, so an AC-only-changed FR sitting alongside a row-changed one used
    to be dropped with no warning at all.

    could-not-determine (R2/AC3, external-review MUST-FIX) survives for what is still
    genuinely undecidable: a real spec delta (``spec_hash`` differs) that changed neither
    any FR row nor any requirement's criteria — an edit to an abstract, a quality
    requirement, or prose between the sections. That is a WARN for a human to adjudicate,
    never a silent pass. A pure refactor leaves ``spec_hash`` identical → no WARN, no gate.
    """
    row_changed = behavior_changed_keys(base, head)
    ac_changed = criteria_changed_keys(head, ac_changed_ids)
    changed = row_changed + [k for k in ac_changed if k not in row_changed]
    if not changed:
        spec_changed = base.get("spec_hash") != head.get("spec_hash")
        return CrossLayerVerdict(changed_keys=[], could_not_determine=bool(spec_changed))

    verdict = CrossLayerVerdict(changed_keys=changed)
    head_active = _active_nodes(head)
    collisions = collision_display_ids(head)
    for key in changed:
        node = head_active.get(key)
        if node is None:
            continue
        disp = node.get("id")
        source = node.get("required_layers_source") or "__missing__"
        priority = node.get("priority", "Must")
        coverage = node.get("coverage") or {}
        ambiguous = disp in collisions
        # DOCUMENTED DEFERRAL (MUST-ADDRESS 5 rebuttal): the frozen ``@FR`` grammar is
        # UN-namespaced, so a passing test tagged ``@FR-XX.YY`` credits this FR regardless of
        # the test's split path — in a MULTI-namespace repo a test under split B could satisfy
        # split A's same-id FR when only A is active (no collision → the guard above never
        # fires). A clean path→split guard is not feasible for the monorepo layout (tests live
        # in shared/tests, plugins/*/tests — never co-located with a spec split), and the
        # pre-rollout monorepo is CONFIRMED single-namespace (only ``01-adopted``, zero
        # cross-namespace id collisions), so it is unaffected. Per-split tag resolution is the
        # carried-forward collision remedy (same track as TT2 doubt #3).
        for layer in node.get("required_layers") or []:
            if coverage.get(layer) == "ok" and not ambiguous:
                continue
            gap = LayerGap(
                disp, key, layer, priority, source,
                "ambiguous_fanout" if ambiguous else "MISSING",
            )
            if ambiguous:
                verdict.advisory.append(gap)
            elif source not in _LEGACY_SOURCES:
                verdict.hard.append(gap)
            else:
                verdict.advisory.append(gap)
    return verdict


__all__ = [
    "collision_display_ids",
    "LayerGap",
    "CrossLayerVerdict",
    "behavior_changed_keys",
    "criteria_changed_keys",
    "evaluate_cross_layer",
]

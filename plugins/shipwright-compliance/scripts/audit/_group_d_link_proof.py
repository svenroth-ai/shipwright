"""D1's SECOND coverage proof — the manifest test link (traceability campaign TT2, Spec §5).

Extracted from :mod:`_group_d_traceability` in the requirements-catalog campaign (S6)
so that module keeps room under its anti-ratchet ceiling while gaining FV-2's
empty-set guards. Pure move: the function body is unchanged, and
``_group_d_traceability`` re-exports it, so every existing caller and import path
keeps working.

Why it is its OWN concern rather than part of D-orphan / D-layer: those two render
*findings* from the manifest, whereas this one refines the D1 **covered set** that
``group_d`` computes from the event log. Different consumer, different output type.
"""

from __future__ import annotations

from pathlib import Path

from scripts.audit._group_d_manifest import (
    LEGACY_SOURCES as _LEGACY_SOURCES,
    collision_ids,
    load_manifest,
    manifest_present,
)


def refine_d1_covered(event_tested: set[str], project_root: Path) -> tuple[set[str], str]:
    """Return ``(covered, note)``. Drop from the event-tested ``covered`` set any FR that
    ALSO owes a manifest test link but has no *executed-passing* one (Spec §5). The two
    proofs never collapse: a tested event for FR-A + a tagged test for a *different* FR-B
    can't cover FR-A (``linked`` keys each FR to its OWN links), and a merely-present but
    skipped link does NOT satisfy it (R1 — the link must be ``coverage==ok``).

    Fail-closed provenance (MUST-FIX 1): the link is required for ``explicit`` **and any
    UNKNOWN / missing** provenance token; only a KNOWN legacy source keeps the event-only
    proof so the pre-TT8 monorepo does not avalanche. A **collision** id is left on the event
    proof (its link is indeterminate — a HARD drop would be a false-red; D-layer surfaces the
    ambiguity advisory instead).

    ``note`` (FIX 3 observability): non-empty when the link-proof was skipped because the
    manifest is PRESENT-but-untrusted (schema-invalid) — a green D1 could then hide a dropped
    link-proof, so the fallback is made visible. Empty for a trusted manifest OR a genuinely
    absent one (absent is expected pre-TT8, not a masked regression)."""
    manifest = load_manifest(project_root)
    if manifest is None:
        note = (" [D1 link-proof skipped: manifest PRESENT but untrusted (schema-invalid) —"
                " event-proof only]" if manifest_present(project_root) else "")
        return event_tested, note
    reqs = manifest.get("requirements") or {}
    collisions = collision_ids(reqs)
    linked: set[str] = set()
    requires_link: set[str] = set()
    for node in reqs.values():
        if node.get("status") != "active":
            continue
        disp = node.get("id")
        if (node.get("required_layers_source") or "__missing__") not in _LEGACY_SOURCES:
            requires_link.add(disp)  # explicit OR unknown/missing token → fail-closed
        if disp not in collisions and any(
                c == "ok" for c in (node.get("coverage") or {}).values()):
            linked.add(disp)  # a non-ambiguous executed-passing link (R1)
    covered = {
        fr for fr in event_tested
        if fr not in requires_link or fr in linked or fr in collisions
    }
    return covered, ""


__all__ = ["refine_d1_covered"]

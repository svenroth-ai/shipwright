"""``D-orphan`` + ``D-layer`` detective checks (traceability campaign TT2, Spec §5).

Both consume the TT1 test-traceability manifest (``.shipwright/compliance/
test-traceability.json``), loaded + schema-validated fail-closed by ``_group_d_manifest``.
Split out of ``group_d.py`` so that file stays under its ADR-096 anti-ratchet cap;
``group_d.run`` calls :func:`traceability_findings`.

Fail-CLOSED is the rule (a false *green* defeats the campaign; a false *red* is merely
noisy). Where a fully fail-closed HARD verdict would create a false-RED, the detector
stays ADVISORY and the remedy is deferred to TT5 rather than crediting a false-green.

- **Manifest trust.** ``_group_d_manifest.load_manifest`` reads the committed artifact but
  **re-validates it against the schema on READ** — a hand-edited / stale / older-collector
  manifest is rejected (→ SKIP), so the closed-vocab guarantee (enums, coverage⇔passing) is
  never merely trusted. The base+head-regenerating ENFORCING gate is TT5's F11 (R3).

- **``D-orphan``.** Surfaces ``manifest.orphans`` fail-closed: ``confirmed_orphan`` → MEDIUM,
  ``possible_orphan`` (incl. a tag fanned onto a collision id) → LOW, an **unknown category**
  → LOW (never silently dropped), ``unmapped`` → informational, ``invalid_tags`` → LOW
  hygiene, and ``fold_defects`` → LOW hygiene (a broken ``## FR-Fold-Map`` means some tag did
  NOT reach its survivor — silent under-coverage of the same class). A tag on a *healthy*
  folded id is no longer an orphan at all: the collector resolves it to the surviving FR.
  The pass branch fires ONLY when there is nothing to surface. The diff-scoped "bare tag
  removal on a *changed* test = HARD" gate needs base+head and is TT5's F11 job.

- **``D-layer``.** An active FR whose ``required_layers`` include a layer with no
  executed-passing tagged test (``coverage[layer] != "ok"``; R1). Severity routing:
  ``explicit`` **or an UNKNOWN provenance token** → HARD by priority (fail-closed — a future
  rename / drift / hand-edit must not silently downgrade); a KNOWN legacy source
  (``inferred_legacy`` / ``defaulted_legacy``) → ADVISORY (the pre-TT8 monorepo valve);
  a **collision (fan-out) id** → ADVISORY regardless of provenance and DEFERRED to TT5 (its
  ``ok`` is never credited — fail-closed vs false-green — but a HARD block would be a
  false-red: such an FR is structurally unsatisfiable under un-namespaced tags, whose
  remedy = namespaced/per-split tags = TT5). ``invalid_layers`` → HARD hygiene.
"""

from __future__ import annotations

from pathlib import Path

from scripts.audit._group_d_manifest import (
    collision_ids,
    fanned_possible_orphans,
    load_manifest,
    manifest_present,
)
from scripts.audit._group_d_render import (
    ADVISORY_LAYER_REASONS,
    fold_defect_line,
    invalid_layer_line,
    invalid_tag_line,
    layer_gap_line,
    orphan_line,
    suggest_layer,
    suggest_orphan,
)
from scripts.audit.audit_adapters import Finding, SOURCE_DETECTIVE_ONLY

_PRIORITY_TO_SEVERITY = {"Must": "HIGH", "Should": "MEDIUM", "May": "LOW"}
_SEV_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_LEGACY_SOURCES = frozenset({"inferred_legacy", "defaulted_legacy"})

#: IMPORTED, not restated — see `_group_d_render.ADVISORY_LAYER_REASONS`. Two
#: literals of this set are what let the verdict and the evidence line disagree.
_ADVISORY_LAYER_REASONS = ADVISORY_LAYER_REASONS
_KNOWN_CATEGORIES = frozenset({"confirmed_orphan", "possible_orphan", "unmapped"})


def _max_sev(sevs: set[str]) -> str:
    return max(sevs, key=lambda s: _SEV_ORDER.get(s, 0)) if sevs else "LOW"


# ---------------------------------------------------------------------------
# D-orphan
# ---------------------------------------------------------------------------


def check_orphan(manifest: dict) -> tuple[str, str, str, list[str], str | None]:
    """(status, severity, detail, evidence, suggested_cmd) for D-orphan."""
    orphans = manifest.get("orphans") or []
    invalid_tags = manifest.get("invalid_tags") or []
    fold_defects = manifest.get("fold_defects") or []
    confirmed = [o for o in orphans if o.get("category") == "confirmed_orphan"]
    possible = [o for o in orphans if o.get("category") == "possible_orphan"]
    unmapped = [o for o in orphans if o.get("category") == "unmapped"]
    # Fail-CLOSED: an orphan whose category is outside the known set is NOT silently
    # dropped into the green branch — it is surfaced (treated as at-least possible).
    other = [o for o in orphans if o.get("category") not in _KNOWN_CATEGORIES]
    fanned = fanned_possible_orphans(manifest)  # collision-credited tags → possible orphans
    possible = possible + other + fanned

    # Clean pass ONLY when nothing needs surfacing. ``unmapped`` alone is informational
    # (R4 — not a stale-feature accusation), but invalid_tags is a real hygiene defect —
    # and so is a broken fold-map: every one of its defects means some tag did NOT get
    # resolved to its survivor, so leaving it invisible would hide silent under-coverage.
    if not confirmed and not possible and not invalid_tags and not fold_defects:
        if unmapped:
            return ("pass", "LOW",
                    f"{len(unmapped)} unmapped test(s) (informational — not orphans)",
                    [orphan_line(o, "unmapped") for o in unmapped], None)
        return ("pass", "MEDIUM", "no test is tagged with a removed/absent FR", [], None)

    severity = "MEDIUM" if confirmed else "LOW"
    evidence = (
        [orphan_line(o, "confirmed") for o in confirmed]
        + [orphan_line(o, "possible") for o in possible]
        + [invalid_tag_line(iv) for iv in invalid_tags]
        + [fold_defect_line(fd) for fd in fold_defects]
        + [orphan_line(o, "unmapped") for o in unmapped]
    )
    parts: list[str] = []
    if confirmed:
        parts.append(f"{len(confirmed)} confirmed (tag → removed/absent FR)")
    if possible:
        parts.append(f"{len(possible)} possible (heuristic / ambiguous fan-out)")
    if invalid_tags:
        parts.append(f"{len(invalid_tags)} malformed @FR tag(s)")
    if fold_defects:
        parts.append(f"{len(fold_defects)} FR-Fold-Map defect(s)")
    head = confirmed[0] if confirmed else (possible[0] if possible else None)
    ref = (f"; e.g. {head.get('test', '?')} → {head.get('tagged_fr')}") if head else ""
    detail = "test-tag defects — " + "; ".join(parts) + ref
    return ("fail", severity, detail, evidence,
            suggest_orphan(head.get("tagged_fr") if head else None))


# ---------------------------------------------------------------------------
# D-layer
# ---------------------------------------------------------------------------


def check_layer(manifest: dict) -> tuple[str, str, str, list[str], str | None]:
    """(status, severity, detail, evidence, suggested_cmd) for D-layer."""
    reqs = manifest.get("requirements") or {}
    collisions = collision_ids(reqs)

    # `invalid_layers` is a MIXED channel since S5 and is split by REASON before
    # it reaches a verdict — see `_ADVISORY_LAYER_REASONS`. Fail-CLOSED: the
    # ADVISORY set is the closed one, so an unrecognised reason blocks.
    all_invalid = manifest.get("invalid_layers") or []
    invalid_advisory = [iv for iv in all_invalid
                        if iv.get("reason") in _ADVISORY_LAYER_REASONS]
    invalid = [iv for iv in all_invalid
               if iv.get("reason") not in _ADVISORY_LAYER_REASONS]

    hard: list[tuple] = []       # explicit / unknown-provenance gaps (FAIL)
    advisory: list[tuple] = []   # legacy + collision-deferred gaps (WARN, no any_fail)
    for node in reqs.values():
        if node.get("status") != "active":
            continue
        # FIX 1 — a MISSING/None/empty key defaults to a NON-legacy sentinel so it routes to
        # HARD (matching refine_d1_covered's None→fail-closed), never fail-open to advisory.
        source = node.get("required_layers_source") or "__missing__"
        coverage = node.get("coverage") or {}
        disp = node.get("id")
        priority = node.get("priority", "Must")
        ambiguous = disp in collisions
        for layer in node.get("required_layers") or []:
            cov = coverage.get(layer)
            # Fail-closed: a collision id's `ok` is NEVER credited (the tag may belong to a
            # different namespace's same-id FR).
            if cov == "ok" and not ambiguous:
                continue
            reason = "ambiguous_fanout" if ambiguous else "MISSING"
            gap = (disp, layer, priority, reason, source)
            if ambiguous:
                advisory.append(gap)                 # DEFERRED to TT5 (false-red avoidance)
            elif source not in _LEGACY_SOURCES:
                hard.append(gap)                     # explicit OR unknown token → fail-closed
            else:
                advisory.append(gap)                 # known legacy → advisory

    inv_lines = [invalid_layer_line(iv) for iv in invalid]
    inv_adv_lines = [invalid_layer_line(iv) for iv in invalid_advisory]

    if hard or invalid:
        sevs = {_PRIORITY_TO_SEVERITY.get(p, "LOW") for (_, _, p, _, _) in hard}
        if invalid:
            sevs.add("MEDIUM")
        parts = []
        if hard:
            parts.append(f"{len(hard)} explicit/unknown FR layer-gap(s)")
        if invalid:
            parts.append(f"{len(invalid)} invalid-layer declaration(s)")
        if advisory:
            parts.append(f"{len(advisory)} advisory gap(s)")
        if invalid_advisory:
            parts.append(f"{len(invalid_advisory)} advisory layer-cell defect(s)")
        detail = "post-rollout coverage gaps — " + "; ".join(parts)
        evidence = ([layer_gap_line(g, "HARD") for g in hard] + inv_lines
                    + [layer_gap_line(g, "advisory") for g in advisory] + inv_adv_lines)
        return "fail", _max_sev(sevs), detail, evidence, suggest_layer()

    if advisory or invalid_advisory:
        # No HARD gaps → pass, but surface the advisory ones (legacy + collision
        # gaps, and the malformed-but-advisory layer cells such as a glued
        # `(inferred)` marker). Reported, never blocking.
        n_amb = sum(1 for g in advisory if g[3] == "ambiguous_fanout")
        detail = (
            f"no explicit FR is missing a required layer; {len(advisory)} advisory gap(s) "
            f"({n_amb} ambiguous fan-out — deferred to TT5; rest pre-rollout legacy)"
        )
        if invalid_advisory:
            detail += f"; {len(invalid_advisory)} advisory layer-cell defect(s)"
        return ("pass", "LOW", detail,
                [layer_gap_line(g, "advisory") for g in advisory] + inv_adv_lines, None)
    return "pass", "LOW", "every active FR is covered at its required layers", [], None


# ---------------------------------------------------------------------------
# D1 link-proof (Spec §5 / deliverable: COVERED requires a tested event AND a link)
# ---------------------------------------------------------------------------


def refine_d1_covered(event_tested: set[str], project_root: Path) -> tuple[set[str], str]:
    """Return ``(covered, note)``. Drop from the event-tested ``covered`` set any FR that
    ALSO owes a manifest test link but has no *executed-passing* one — the second, SEPARATE
    proof (Spec §5). The two proofs never collapse: a tested event for FR-A + a tagged test
    for a *different* FR-B can't cover FR-A (``linked`` keys each FR to its OWN links), and a
    merely-present but skipped link does NOT satisfy it (R1 — the link must be ``coverage==ok``).

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


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

_NAMES = {
    "D-orphan": "Tests tagged with a removed/absent FR",
    "D-layer": "Active FR missing an executed-passing test at a required layer",
}


def _finding(check_id: str, result: tuple) -> Finding:
    status, severity, detail, evidence, suggest = result
    return Finding(
        group="D", check_id=check_id, name=_NAMES[check_id],
        severity=severity, source=SOURCE_DETECTIVE_ONLY, status=status,
        detail=detail, evidence=list(evidence),
        suggested_iterate_cmd=suggest if status == "fail" else None,
    )


def traceability_findings(project_root: Path) -> list[Finding]:
    """Run D-orphan + D-layer. Manifest absent / untrusted → both SKIP (fail-closed)."""
    manifest = load_manifest(project_root)
    if manifest is None:
        skip = ("skip", "MEDIUM",
                "test-traceability manifest absent, not v3, or schema-invalid", [], None)
        return [_finding("D-orphan", skip), _finding("D-layer", skip)]
    out: list[Finding] = []
    for check_id, fn in (("D-orphan", check_orphan), ("D-layer", check_layer)):
        try:
            out.append(_finding(check_id, fn(manifest)))
        except Exception as exc:  # noqa: BLE001 — never crash the whole group
            out.append(Finding(
                group="D", check_id=check_id, name=_NAMES[check_id],
                severity="HIGH", source=SOURCE_DETECTIVE_ONLY, status="fail",
                detail=f"check raised {type(exc).__name__}: {exc}",
            ))
    return out


__all__ = ["load_manifest", "check_orphan", "check_layer", "refine_d1_covered",
           "traceability_findings"]

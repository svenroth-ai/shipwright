"""``D-orphan`` + ``D-layer`` detective checks (traceability campaign TT2, Spec §5).

Both consume the TT1 test-traceability manifest (``.shipwright/compliance/
test-traceability.json``). Split out of ``group_d.py`` so that file stays under its
ADR-096 anti-ratchet cap; ``group_d.run`` calls :func:`traceability_findings`.

Fail-closed design (this is a gate — a false *green* is worse than a false *red*):

- **Manifest source (R3).** The committed manifest is derived / RTM-visibility only;
  the two *enforcing* iterate gates (TT5 F11) regenerate base+head themselves. This
  *detective* runs post-merge and is non-blocking, and ``update_compliance`` regenerates
  the committed manifest every phase (fresh at audit time), so it reads the committed
  artifact — but an **absent / malformed / non-v2** manifest is a SKIP (no proof ≠ pass),
  never a silent pass.

- **``D-orphan``.** Surfaces ``manifest.orphans`` (a test tagged with a removed/absent
  FR). The collector already resolves the frozen un-namespaced ``@FR-XX.YY`` fan-out
  correctly — a tag is an orphan only when it resolves to NO *active* FR in ANY namespace
  (``fr_removed`` if a removed match exists, else ``fr_absent``); a tag that resolves to a
  live FR anywhere is filed as coverage, never an orphan — so D-orphan cannot false-flag a
  live tag. ``category`` is respected: ``confirmed_orphan`` → MEDIUM (the session class),
  ``possible_orphan`` → LOW, ``unmapped`` → informational (never a stale-feature
  accusation, R4). The diff-scoped "bare tag removal on a *changed* test = HARD" gate is
  TT5's F11 job (needs base+head); this detective sees only the current manifest.

- **``D-layer``.** An active FR whose ``required_layers`` include a layer with no
  executed-passing tagged test there (``coverage[layer] != "ok"``; R1 — a green-but-skipped
  test is ``MISSING``, not ``ok``). Provenance is the release valve (R4 / carry-forward):
  ``explicit`` (post-rollout) FRs FAIL, severity by priority (Must=HIGH/Should=MED/May=LOW)
  and count toward ``any_fail``; ``inferred_legacy`` / ``defaulted_legacy`` FRs are
  ADVISORY (surfaced, but ``status="pass"`` so the pre-TT8 monorepo — all-MISSING, no run
  evidence yet — does not drown in HIGH findings). ``invalid_layers`` (author declared an
  unparseable layer) is a HARD hygiene finding. **Namespace fan-out:** a display id shared
  by ≥2 active requirements can be false-satisfied by a fanned tag, so an ``ok`` on a
  collision FR is treated as NOT-confirmed (fail-closed) rather than credited.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.audit.audit_adapters import Finding, SOURCE_DETECTIVE_ONLY

_MANIFEST_REL = ".shipwright/compliance/test-traceability.json"
_LAYER_ORDER = ("unit", "integration", "e2e")
_PRIORITY_TO_SEVERITY = {"Must": "HIGH", "Should": "MEDIUM", "May": "LOW"}
_SEV_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_LEGACY_SOURCES = frozenset({"inferred_legacy", "defaulted_legacy"})


def _max_sev(sevs: set[str]) -> str:
    return max(sevs, key=lambda s: _SEV_ORDER.get(s, 0)) if sevs else "LOW"


def load_manifest(project_root: Path) -> dict | None:
    """Read the committed v2 manifest. ``None`` when absent / unreadable / not v2.

    ``None`` drives a SKIP upstream — a missing proof is never a pass (fail-closed)."""
    path = Path(project_root) / _MANIFEST_REL
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        return None
    if not isinstance(data.get("requirements"), dict):
        return None
    return data


# ---------------------------------------------------------------------------
# D-orphan
# ---------------------------------------------------------------------------


def _suggest_orphan(fr: str | None) -> str:
    # The specific test path stays in *evidence* (untrusted repo content), never in this
    # copy-paste command — a test id with a quote/shell metachar would otherwise break the
    # command (external-review MED). ``fr`` is schema-pinned ``FR-\d{2}\.\d{2}`` (or None),
    # so it is safe to interpolate.
    target = f"for {fr} " if fr else ""
    return (
        f"/shipwright-iterate --type change \"retarget or retire the orphaned "
        f"test(s) {target}— see .shipwright/compliance/test-traceability.json\""
    )


def check_orphan(manifest: dict) -> tuple[str, str, str, list[str], str | None]:
    """(status, severity, detail, evidence, suggested_cmd) for D-orphan."""
    orphans = manifest.get("orphans") or []
    confirmed = [o for o in orphans if o.get("category") == "confirmed_orphan"]
    possible = [o for o in orphans if o.get("category") == "possible_orphan"]
    unmapped = [o for o in orphans if o.get("category") == "unmapped"]

    def _line(o: dict, tag: str) -> str:
        fr = o.get("tagged_fr")
        reason = o.get("reason", "")
        target = f"→ {fr}" if fr else "(no live FR)"
        return f"{o.get('test', '?')} {target} ({reason}) [{tag}]"

    # unmapped alone is NOT an accusation (R4) — surface, never fail on it.
    if not confirmed and not possible:
        if unmapped:
            ev = [_line(o, "unmapped") for o in unmapped]
            return ("pass", "LOW",
                    f"{len(unmapped)} unmapped test(s) (informational — not orphans)",
                    ev, None)
        return ("pass", "MEDIUM",
                "no test is tagged with a removed/absent FR", [], None)

    severity = "MEDIUM" if confirmed else "LOW"
    evidence = ([_line(o, "confirmed") for o in confirmed]
                + [_line(o, "possible") for o in possible]
                + [_line(o, "unmapped") for o in unmapped])
    parts: list[str] = []
    if confirmed:
        parts.append(f"{len(confirmed)} confirmed (tag → removed/absent FR)")
    if possible:
        parts.append(f"{len(possible)} possible (heuristic)")
    head = confirmed[0] if confirmed else possible[0]
    detail = (
        "test(s) tagged with a dead/removed FR — " + "; ".join(parts)
        + f"; e.g. {head.get('test', '?')} → {head.get('tagged_fr')}"
    )
    return ("fail", severity, detail, evidence,
            _suggest_orphan(head.get("tagged_fr")))


# ---------------------------------------------------------------------------
# D-layer
# ---------------------------------------------------------------------------


def _collision_ids(reqs: dict) -> set[str]:
    """Display ids owned by ≥2 ACTIVE requirement nodes (fan-out ambiguity)."""
    seen: dict[str, int] = {}
    for node in reqs.values():
        if node.get("status") == "active":
            disp = node.get("id")
            seen[disp] = seen.get(disp, 0) + 1
    return {i for i, n in seen.items() if n > 1}


def check_layer(manifest: dict) -> tuple[str, str, str, list[str], str | None]:
    """(status, severity, detail, evidence, suggested_cmd) for D-layer."""
    reqs = manifest.get("requirements") or {}
    invalid = manifest.get("invalid_layers") or []
    collisions = _collision_ids(reqs)

    hard: list[tuple] = []       # explicit-provenance gaps (FAIL)
    advisory: list[tuple] = []   # legacy-provenance gaps (WARN, no any_fail)
    for node in reqs.values():
        if node.get("status") != "active":
            continue
        source = node.get("required_layers_source", "defaulted_legacy")
        coverage = node.get("coverage") or {}
        disp = node.get("id")
        priority = node.get("priority", "Must")
        ambiguous = disp in collisions
        for layer in node.get("required_layers") or []:
            cov = coverage.get(layer)
            # Fail-closed: an `ok` on a fanned-out (collision) FR is NOT confirmed
            # coverage — the tag may exercise a different namespace's same-id FR.
            if cov == "ok" and not ambiguous:
                continue
            reason = "ambiguous_fanout" if (ambiguous and cov == "ok") else "MISSING"
            gap = (disp, layer, priority, reason, source)
            (hard if source == "explicit" else advisory).append(gap)

    def _gap_line(g: tuple, tag: str) -> str:
        disp, layer, priority, reason, source = g
        return f"{disp} [{layer}] ({priority}) — {reason} [{tag}, {source}]"

    inv_lines = [
        f"{iv.get('fr', '?')} invalid Layers cell {iv.get('raw', '')!r} [HARD, explicit]"
        for iv in invalid
    ]

    if hard or invalid:
        sevs = {_PRIORITY_TO_SEVERITY.get(p, "LOW") for (_, _, p, _, _) in hard}
        if invalid:
            sevs.add("MEDIUM")
        severity = _max_sev(sevs)
        parts = []
        if hard:
            parts.append(f"{len(hard)} explicit FR layer-gap(s)")
        if invalid:
            parts.append(f"{len(invalid)} invalid-layer declaration(s)")
        if advisory:
            parts.append(f"{len(advisory)} legacy advisory gap(s)")
        detail = "post-rollout coverage gaps — " + "; ".join(parts)
        evidence = ([_gap_line(g, "HARD") for g in hard] + inv_lines
                    + [_gap_line(g, "advisory") for g in advisory])
        suggest = (
            "/shipwright-iterate --type change \"add an executed-passing test at the "
            "missing layer(s) — see .shipwright/compliance/audit-report.md\""
        )
        return "fail", severity, detail, evidence, suggest

    # No explicit gaps → pass; still surface any legacy advisory gaps (WARN).
    if advisory:
        detail = (
            f"no explicit FR is missing a required layer; "
            f"{len(advisory)} legacy advisory gap(s) (pre-rollout provenance — WARN)"
        )
        return ("pass", "LOW", detail,
                [_gap_line(g, "advisory") for g in advisory], None)
    return "pass", "LOW", "every active FR is covered at its required layers", [], None


# ---------------------------------------------------------------------------
# D1 link-proof (Spec §5 / deliverable: COVERED requires a tested event AND a link)
# ---------------------------------------------------------------------------


def refine_d1_covered(event_tested: set[str], project_root: Path) -> set[str]:
    """Drop from the event-tested ``covered`` set any FR that ALSO owes a manifest test
    link but has none — the second, SEPARATE proof (event-coverage AND test-link-coverage,
    Spec §5). The two proofs never collapse: a tested event for FR-A + a tagged test for a
    *different* FR-B can't cover FR-A, because ``linked`` keys each FR to its OWN links.

    The link proof is provenance-gated (Spec §9 landmine / carry-forward #2): it bites only
    for ``explicit`` (post-rollout) FRs; ``legacy``/pre-rollout FRs keep the event-only proof
    so the pre-TT8 monorepo (no ``@FR`` tags yet) does not avalanche into all-FR D1 failures.
    Fail-closed on fan-out: a link on a display id shared across namespaces is NOT counted
    (it may exercise a different namespace's same-id FR). No manifest → event-proof only."""
    manifest = load_manifest(project_root)
    if manifest is None:
        return event_tested
    reqs = manifest.get("requirements") or {}
    collisions = _collision_ids(reqs)
    linked: set[str] = set()
    explicit: set[str] = set()
    for node in reqs.values():
        if node.get("status") != "active":
            continue
        disp = node.get("id")
        if node.get("required_layers_source") == "explicit":
            explicit.add(disp)
        if disp not in collisions and any((node.get("tests") or {}).values()):
            linked.add(disp)
    return {fr for fr in event_tested if fr not in explicit or fr in linked}


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
    """Run D-orphan + D-layer. Manifest absent → both SKIP (fail-closed)."""
    manifest = load_manifest(project_root)
    if manifest is None:
        skip = ("skip", "MEDIUM", "test-traceability manifest absent or not v2", [], None)
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


__all__ = ["load_manifest", "check_orphan", "check_layer", "traceability_findings"]

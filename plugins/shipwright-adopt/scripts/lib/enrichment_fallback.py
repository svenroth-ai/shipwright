"""Generate a deterministic minimal enrichment when Layer-2 produced none (4.4).

Prior behavior: missing enrichment.json silently fell back to using
snapshot+routes only — features got TBD descriptions and ADRs were
missing. The fallback now produces a structured, schema-valid
enrichment.json with NO hallucinated prose: every text field is
clearly a placeholder. Callers (and the SKILL.md handoff) read the
`_fallback: true` marker to surface "Layer-2 was skipped" loudly.
"""

from __future__ import annotations

from typing import Any


def build_fallback_enrichment(
    snapshot: dict[str, Any],
    routes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a schema-valid enrichment dict from snapshot + routes.

    No invented prose. Features come from the union of AST features
    (snapshot.features) and crawl routes; descriptions are placeholders;
    ADRs are empty (the operator is expected to add them via
    /shipwright-iterate). The `_fallback: true` marker tells downstream
    consumers that real Layer-2 enrichment was skipped.
    """
    routes = routes or []
    primary_language = snapshot.get("stack", {}).get("primary_language", "unknown")

    # Union AST features + crawl routes by route key, no duplicates
    ast_features = snapshot.get("features", []) or []
    seen: set[str] = set()
    features: list[dict[str, Any]] = []
    for f in ast_features:
        route = f.get("route")
        if not route or route in seen:
            continue
        seen.add(route)
        features.append({
            "route": route,
            "label": f.get("route") or "TBD",
            "description": "TBD — Layer-2 enrichment skipped, refine via /shipwright-iterate.",
            "acceptance_draft": "TBD",
        })
    for r in routes:
        url = r.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        features.append({
            "route": url,
            "label": r.get("title") or url,
            "description": "TBD — Layer-2 enrichment skipped, refine via /shipwright-iterate.",
            "acceptance_draft": "TBD",
        })

    layers = snapshot.get("folders", {}).get("layers", [])
    diagram_lines = ["```", "  (auto-generated fallback diagram)", ""]
    for layer in layers:
        diagram_lines.append(f"  [{layer.get('name', '?')}]")
        for path in (layer.get("paths") or [])[:5]:
            diagram_lines.append(f"    - {path}")
    diagram_lines.append("```")
    architecture_diagram = "\n".join(diagram_lines)

    return {
        "_fallback": True,
        "product_description": (
            f"TBD (auto-generated fallback). Primary language: {primary_language}. "
            "Layer-2 enrichment was skipped — refine this abstract via "
            "/shipwright-iterate before relying on it."
        ),
        "features": features,
        "architecture_prose": (
            "TBD (fallback). Folder layers were extracted deterministically from "
            "the codebase — see the diagram above. No data-flow narrative "
            "available without Layer-2 enrichment."
        ),
        "architecture_diagram": architecture_diagram,
        "conventions_prose": (
            "TBD (fallback). Linter/formatter detected in the snapshot; deeper "
            "project-specific conventions require Layer-2 enrichment."
        ),
        "adrs": [],
    }

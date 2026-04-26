"""Verify enrichment_fallback generates a valid minimal enrichment from
snapshot + routes (4.4)."""

from __future__ import annotations

from lib.enrichment_fallback import build_fallback_enrichment
from lib.enrichment_schema import validate_enrichment


def _basic_snapshot() -> dict:
    return {
        "stack": {"primary_language": "typescript"},
        "features": [
            {"route": "/dashboard", "source_file": "src/pages/dashboard.tsx", "framework": "next-pages-router"},
        ],
        "folders": {
            "layers": [
                {"name": "presentation", "paths": ["src/pages"]},
                {"name": "domain", "paths": ["src/lib"]},
            ],
        },
        "conventions": {"linter": "eslint", "formatter": "prettier"},
        "git": {"major_refactor_commits": []},
    }


def test_fallback_passes_schema_validation() -> None:
    result = build_fallback_enrichment(_basic_snapshot(), routes=[])
    # Must be schema-valid so adopt can proceed without hallucinated prose
    validate_enrichment(result)


def test_fallback_marks_itself_as_fallback() -> None:
    """The is_fallback flag tells callers (and SKILL.md handoff) to be loud
    about the absence of real Layer-2 enrichment."""
    result = build_fallback_enrichment(_basic_snapshot(), routes=[])
    assert result.get("_fallback") is True


def test_fallback_features_from_ast(tmp_path) -> None:
    """When no crawl routes available, AST features show up — labeled, not
    hallucinated."""
    snapshot = _basic_snapshot()
    result = build_fallback_enrichment(snapshot, routes=[])
    routes = [f["route"] for f in result["features"]]
    assert "/dashboard" in routes
    # Description must be a placeholder, not invented prose
    dashboard = next(f for f in result["features"] if f["route"] == "/dashboard")
    assert "TBD" in dashboard["description"] or "placeholder" in dashboard["description"].lower()


def test_fallback_features_union_with_crawl_routes() -> None:
    """When BOTH AST and crawl exist, the fallback features list unions them."""
    snapshot = _basic_snapshot()
    routes = [
        {"url": "/", "title": "Home"},
        {"url": "/login", "title": "Login"},
    ]
    result = build_fallback_enrichment(snapshot, routes=routes)
    feature_routes = {f["route"] for f in result["features"]}
    assert "/dashboard" in feature_routes  # from AST
    assert "/" in feature_routes           # from crawl
    assert "/login" in feature_routes      # from crawl


def test_fallback_no_invented_prose() -> None:
    """The whole point: no plausible-sounding lies. product_description is
    deterministic and obviously placeholder-ish."""
    result = build_fallback_enrichment(_basic_snapshot(), routes=[])
    desc = result["product_description"].lower()
    assert "fallback" in desc or "tbd" in desc or "placeholder" in desc or "auto-generated" in desc

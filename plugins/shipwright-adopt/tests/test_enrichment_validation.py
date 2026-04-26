"""Verify enrichment.json schema validation (4.4 — fail loud, not silent)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.enrichment_schema import EnrichmentValidationError, validate_enrichment


def test_minimal_valid_enrichment_passes() -> None:
    data = {
        "product_description": "An app that does X.",
        "features": [],
        "architecture_prose": "Single-tier.",
        "architecture_diagram": "```\n(diagram)\n```",
        "conventions_prose": "Use Conventional Commits.",
        "adrs": [],
    }
    validate_enrichment(data)  # no raise


def test_missing_top_level_key_raises() -> None:
    data = {
        # missing product_description
        "features": [],
        "architecture_prose": "x",
        "architecture_diagram": "x",
        "conventions_prose": "x",
        "adrs": [],
    }
    with pytest.raises(EnrichmentValidationError, match="product_description"):
        validate_enrichment(data)


def test_wrong_type_raises() -> None:
    data = {
        "product_description": "ok",
        "features": "not a list",  # wrong type
        "architecture_prose": "x",
        "architecture_diagram": "x",
        "conventions_prose": "x",
        "adrs": [],
    }
    with pytest.raises(EnrichmentValidationError, match="features"):
        validate_enrichment(data)


def test_feature_missing_route_raises() -> None:
    data = {
        "product_description": "ok",
        "features": [{"label": "x", "description": "y"}],  # no `route`
        "architecture_prose": "x",
        "architecture_diagram": "x",
        "conventions_prose": "x",
        "adrs": [],
    }
    with pytest.raises(EnrichmentValidationError, match="route"):
        validate_enrichment(data)


def test_adr_missing_required_fields_raises() -> None:
    data = {
        "product_description": "ok",
        "features": [],
        "architecture_prose": "x",
        "architecture_diagram": "x",
        "conventions_prose": "x",
        "adrs": [{"context": "x"}],  # missing decision + consequences
    }
    with pytest.raises(EnrichmentValidationError):
        validate_enrichment(data)


def test_validate_enrichment_file_returns_data(tmp_path: Path) -> None:
    """When called with a path, returns parsed dict on success."""
    from lib.enrichment_schema import validate_enrichment_file

    valid = {
        "product_description": "ok",
        "features": [],
        "architecture_prose": "x",
        "architecture_diagram": "x",
        "conventions_prose": "x",
        "adrs": [],
    }
    p = tmp_path / "enrichment.json"
    p.write_text(json.dumps(valid), encoding="utf-8")
    data = validate_enrichment_file(p)
    assert data["product_description"] == "ok"


def test_validate_enrichment_file_invalid_raises(tmp_path: Path) -> None:
    """An invalid enrichment.json must raise — adopt should fail loud, not
    silently drop to snapshot+routes only."""
    from lib.enrichment_schema import validate_enrichment_file

    p = tmp_path / "enrichment.json"
    p.write_text(json.dumps({"product_description": "ok"}), encoding="utf-8")  # missing required keys
    with pytest.raises(EnrichmentValidationError):
        validate_enrichment_file(p)

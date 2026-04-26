"""Schema validation for `.shipwright/adopt/enrichment.json` (4.4).

Originally Step B.8 (Layer 2 Enrichment) was "Claude-inline" — the
calling Claude was expected to read sources and write enrichment.json.
If it skipped or wrote invalid JSON, Step E silently used snapshot+routes
only — features got TBD descriptions and ADRs were missing.

This validator turns silent skip into a loud failure so the operator
knows enrichment was incomplete BEFORE the adoption commit lands.

Dependency-free by design — adopt's pyproject keeps no `jsonschema`
dependency. The schema is small enough to hand-code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class EnrichmentValidationError(ValueError):
    """Raised when enrichment.json doesn't match the documented schema."""


_REQUIRED_TOP_LEVEL: dict[str, type] = {
    "product_description": str,
    "features": list,
    "architecture_prose": str,
    "architecture_diagram": str,
    "conventions_prose": str,
    "adrs": list,
}


def validate_enrichment(data: Any) -> None:
    """Raise EnrichmentValidationError if `data` doesn't match the schema."""
    if not isinstance(data, dict):
        raise EnrichmentValidationError(
            f"enrichment must be a JSON object; got {type(data).__name__}"
        )
    for key, expected in _REQUIRED_TOP_LEVEL.items():
        if key not in data:
            raise EnrichmentValidationError(f"missing required key: {key!r}")
        val = data[key]
        if not isinstance(val, expected):
            raise EnrichmentValidationError(
                f"{key!r} must be {expected.__name__}; got {type(val).__name__}"
            )

    # features[]: each must have a `route` (string)
    for i, feat in enumerate(data["features"]):
        if not isinstance(feat, dict):
            raise EnrichmentValidationError(f"features[{i}] must be an object")
        if "route" not in feat:
            raise EnrichmentValidationError(f"features[{i}] missing required field: 'route'")
        if not isinstance(feat["route"], str):
            raise EnrichmentValidationError(
                f"features[{i}].route must be a string"
            )

    # adrs[]: each must have context + decision + consequences
    for i, adr in enumerate(data["adrs"]):
        if not isinstance(adr, dict):
            raise EnrichmentValidationError(f"adrs[{i}] must be an object")
        for required in ("context", "decision", "consequences"):
            if required not in adr:
                raise EnrichmentValidationError(
                    f"adrs[{i}] missing required field: {required!r}"
                )


def validate_enrichment_file(path: Path) -> dict[str, Any]:
    """Read + parse + validate. Returns the parsed dict on success."""
    try:
        body = path.read_text(encoding="utf-8")
    except OSError as e:
        raise EnrichmentValidationError(f"cannot read {path}: {e}") from e
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise EnrichmentValidationError(
            f"enrichment.json at {path} is not valid JSON: {e.msg} "
            f"(line {e.lineno}, col {e.colno})"
        ) from e
    validate_enrichment(data)
    return data

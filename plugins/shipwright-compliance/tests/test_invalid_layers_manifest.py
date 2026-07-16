"""TT3 §11-R4 — an unrecognized FR `Layers` cell surfaces in the manifest.

A headed `Layers` cell with no valid canonical layer (an author typo/synonym like
`int, db`) must NOT be silently demoted to advisory legacy: the FR stays `explicit`
(so D-layer's post-rollout hard gate still fires) and the raw token is surfaced in the
manifest's `invalid_layers` array so the finding can name it. The field is additive +
optional, so the manifest stays schema-valid.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import jsonschema  # noqa: E402

from scripts.lib.collectors.test_links import build_manifest  # noqa: E402

_SCHEMA = _HERE.parent / "scripts" / "lib" / "traceability_schema.json"

_SPEC = """# Spec
## Functional Requirements
| ID | Requirement | Priority | Layers |
|----|-------------|----------|--------|
| FR-06.01 | Persist orders | Must | int, db |
| FR-06.02 | Show dashboard | Must | unit, e2e |
"""


def _validator():
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def _req(manifest: dict, fr_id: str) -> dict:
    return next(r for r in manifest["requirements"].values() if r["id"] == fr_id)


def test_invalid_layers_cell_surfaced_and_fr_stays_explicit(tmp_path):
    (tmp_path / "spec.md").write_text(_SPEC, encoding="utf-8")
    manifest = build_manifest(
        tmp_path, spec_files=[tmp_path / "spec.md"], test_roots=[tmp_path],
        evidence={}, enumerate_untagged=True,
    )
    # still schema-valid (invalid_layers is additive + optional)
    assert not list(_validator().iter_errors(manifest))
    entries = manifest["invalid_layers"]
    assert any(e["fr"] == "FR-06.01" and e["raw"] == "int, db"
               and e["reason"] == "no_canonical_layer" for e in entries)
    # the well-formed FR is not flagged
    assert not any(e["fr"] == "FR-06.02" for e in entries)
    # the typo'd FR is kept explicit (NOT demoted to advisory legacy)
    assert _req(manifest, "FR-06.01")["required_layers_source"] == "explicit"

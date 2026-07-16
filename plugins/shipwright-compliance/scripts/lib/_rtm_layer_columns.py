"""Per-FR ``Unit | Integration | E2E`` coverage columns for the RTM (traceability TT2).

``rtm_generator.py`` is a grandfathered file at its anti-ratchet cap, so the manifest-
driven layer-coverage logic lives here (Spec §5 / AC1). Reads the committed
test-traceability manifest (TT1 — derived / RTM-visibility only, R3) and renders a
coverage-at-layer glyph (``ok`` / ``MISSING`` / ``n/a``) per FR, so a matrix row can
show "unit yes, E2E no" instead of a single layer-blind number.

Row → manifest matching is by the **namespaced key** ``split::FR-id`` (the manifest
namespace is the split-dir name, exactly ``RequirementInfo.split``), so a display id
shared across splits resolves to *this* row's own split — the frozen-grammar fan-out
(one tag crediting every same-id namespace) cannot mislabel a specific row. When no
exact namespaced entry exists, a same-display-id fallback merges *conservatively*
(``MISSING`` wins over ``ok``) so visibility never over-reports. The enforcing
fail-closed treatment of that ambiguity is D-layer's job (``_group_d_traceability``).
"""

from __future__ import annotations

import json
from pathlib import Path

_MANIFEST_REL = ".shipwright/compliance/test-traceability.json"
_LAYERS = ("unit", "integration", "e2e")
_ABSENT = "—"
# Conservative merge precedence when a display id spans namespaces (worst wins).
_WORST = ("MISSING", "n/a", "ok")


class LayerIndex:
    """Namespaced + display-id lookup of per-layer coverage glyphs."""

    __slots__ = ("by_key", "by_id")

    def __init__(self, by_key: dict, by_id: dict) -> None:
        self.by_key = by_key  # "split::FR-id" -> {layer: glyph}
        self.by_id = by_id    # "FR-id" -> {layer: glyph} (conservative merge)


def _merge(into: dict, coverage: dict) -> None:
    """Fold ``coverage`` into ``into`` keeping the worst (most conservative) glyph."""
    for layer in _LAYERS:
        cov = coverage.get(layer)
        if cov not in _WORST:
            continue
        cur = into.get(layer)
        if cur is None or _WORST.index(cov) < _WORST.index(cur):
            into[layer] = cov


def load_layer_index(project_root: Path) -> LayerIndex:
    """Build the layer index from the committed v2 manifest (empty on absence)."""
    by_key: dict[str, dict[str, str]] = {}
    by_id: dict[str, dict[str, str]] = {}
    path = Path(project_root) / _MANIFEST_REL
    if not path.exists():
        return LayerIndex(by_key, by_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LayerIndex(by_key, by_id)
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        return LayerIndex(by_key, by_id)
    reqs = data.get("requirements")
    if not isinstance(reqs, dict):
        return LayerIndex(by_key, by_id)
    for key, node in reqs.items():
        if not isinstance(node, dict):
            continue
        coverage = node.get("coverage") or {}
        cells = {l: coverage[l] for l in _LAYERS if coverage.get(l) in _WORST}
        by_key[key] = cells
        disp = node.get("id")
        if isinstance(disp, str):
            _merge(by_id.setdefault(disp, {}), coverage)
    return LayerIndex(by_key, by_id)


def layer_cells(index: LayerIndex, split: str, fr_id: str) -> tuple[str, str, str]:
    """Return ``(unit, integration, e2e)`` glyphs for one RTM row.

    Exact ``split::FR-id`` match first; else a conservative same-id merge; else
    ``—`` (the FR isn't in the manifest — e.g. no manifest, or a not-yet-collected
    test root). A required-but-uncovered layer reads ``MISSING`` (never a bare —)."""
    cells = index.by_key.get(f"{split}::{fr_id}")
    if cells is None:
        cells = index.by_id.get(fr_id)
    if not cells:
        return _ABSENT, _ABSENT, _ABSENT
    return tuple(cells.get(l, _ABSENT) for l in _LAYERS)  # type: ignore[return-value]


__all__ = ["LayerIndex", "load_layer_index", "layer_cells"]

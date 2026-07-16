"""Per-FR ``Unit | Integration | E2E`` coverage columns for the RTM (traceability TT2).

``rtm_generator.py`` is a grandfathered file at its anti-ratchet cap, so the manifest-
driven layer-coverage logic lives here (Spec §5 / AC1). Reads the committed
test-traceability manifest (TT1 — derived / RTM-visibility only, R3) and renders a
coverage-at-layer glyph (``ok`` / ``MISSING`` / ``n/a`` / ``?`` / ``—``) per FR.

Rows are matched to a manifest **node** by the namespaced key ``split::FR-id``. That
resolves the correct *node*, but the node's coverage VALUE may itself be fanned: the frozen
un-namespaced ``@FR-XX.YY`` grammar carries no namespace, so a bare tag is filed into every
node sharing that display id (incl. a ``removed`` occurrence). A display id shared across
namespaces is therefore **ambiguous**, and its ``ok`` is rendered ``?`` (not credited) —
mirroring the ``D-layer`` detective, which fail-closes the identical value as
``ambiguous_fanout``. The two must never disagree (RTM green while the gate flags it). The
false-red remedy (namespaced / per-split tags) is deferred to TT5; here we only avoid the
false-green.
"""

from __future__ import annotations

import json
from pathlib import Path

_MANIFEST_REL = ".shipwright/compliance/test-traceability.json"
_LAYERS = ("unit", "integration", "e2e")
_ABSENT = "—"
_AMBIGUOUS = "?"
# Conservative merge precedence when a display id spans namespaces (worst wins).
_WORST = ("MISSING", "n/a", "ok")


class LayerIndex:
    """Namespaced + display-id lookup of per-layer coverage glyphs, plus collision ids."""

    __slots__ = ("by_key", "by_id", "collisions")

    def __init__(self, by_key: dict, by_id: dict, collisions: set) -> None:
        self.by_key = by_key            # "split::FR-id" -> {layer: glyph}
        self.by_id = by_id              # "FR-id" -> {layer: glyph} (conservative merge)
        self.collisions = collisions    # display ids shared by >=2 nodes (active or removed)


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
    seen: dict[str, int] = {}
    path = Path(project_root) / _MANIFEST_REL
    if not path.exists():
        return LayerIndex(by_key, by_id, set())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LayerIndex(by_key, by_id, set())
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        return LayerIndex(by_key, by_id, set())
    reqs = data.get("requirements")
    if not isinstance(reqs, dict):
        return LayerIndex(by_key, by_id, set())
    for key, node in reqs.items():
        if not isinstance(node, dict):
            continue
        disp = node.get("id")
        if isinstance(disp, str):
            seen[disp] = seen.get(disp, 0) + 1  # count active AND removed (ambiguity)
        coverage = node.get("coverage") or {}
        by_key[key] = {l: coverage[l] for l in _LAYERS if coverage.get(l) in _WORST}
        if isinstance(disp, str):
            _merge(by_id.setdefault(disp, {}), coverage)
    collisions = {i for i, n in seen.items() if n > 1}
    return LayerIndex(by_key, by_id, collisions)


def layer_cells(index: LayerIndex, split: str, fr_id: str) -> tuple[str, str, str]:
    """Return ``(unit, integration, e2e)`` glyphs for one RTM row.

    Exact ``split::FR-id`` match first; else a conservative same-id merge; else ``—``. A
    required-but-uncovered layer reads ``MISSING``. A ``ok`` on a fan-out **collision**
    display id is rendered ``?`` (ambiguous, not credited) — the RTM must agree with
    ``D-layer``, which fail-closes the same value."""
    cells = index.by_key.get(f"{split}::{fr_id}")
    if cells is None:
        cells = index.by_id.get(fr_id)
    if not cells:
        return _ABSENT, _ABSENT, _ABSENT
    ambiguous = fr_id in index.collisions
    out = []
    for layer in _LAYERS:
        glyph = cells.get(layer, _ABSENT)
        out.append(_AMBIGUOUS if (ambiguous and glyph == "ok") else glyph)
    return out[0], out[1], out[2]


__all__ = ["LayerIndex", "load_layer_index", "layer_cells"]

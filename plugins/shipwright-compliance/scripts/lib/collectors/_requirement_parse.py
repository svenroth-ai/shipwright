"""Parse a ``spec.md`` FR table into the frozen ``requirement_model.Requirement``.

Traceability campaign TT1. The one versioned requirement model
(``shared/scripts/lib/requirement_model.py``, R5) is the shape every traceability
consumer shares; this is the compliance-side parser that *builds* those objects
from a spec.md. It does not fork the model — it constructs it.

Column-aware, so it reads BOTH shapes Shipwright writes without confusing them
(the 4th cell means different things in each):

* traceability shape — ``| FR | Description | Priority | Layers |``
* adopt shape (ADR-031) — ``| ID | Name | Priority | Description | Source |``

The header row's column names drive the mapping (``Layers`` / ``Description`` /
``Priority``); a spec with no recognisable header falls back to positional cells.

``Layers`` column → ``required_layers`` provenance (Spec D2 / R4):

* present + non-empty  → ``required_layers_source = "explicit"``
* absent/empty + a UI/flow signal in the title → ``inferred_legacy`` → ``(e2e,)``
* absent/empty + no signal → ``defaulted_legacy`` → ``(unit,)`` (every FR ⇒ unit)

Rows under a ``## Removed Requirements`` heading are parsed with ``status="removed"``
(their tagged tests become orphans, never live coverage).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")

# UI/flow words → a bare FR (no Layers column) is inferred to require e2e. Matched
# on whole words (not substrings) so "view" never fires on "review"/"overview".
_UI_FLOW_WORDS: frozenset[str] = frozenset({
    "dashboard", "page", "pages", "screen", "screens", "view", "views", "button",
    "buttons", "click", "clicks", "display", "displays", "show", "shows", "render",
    "renders", "navigate", "login", "logout", "modal", "menu", "banner", "form",
    "clipboard", "widget", "scroll", "upload", "download", "toast", "wizard",
})
_UI_FLOW_PHRASES: tuple[str, ...] = ("sign in", "sign-in", "log in")

# Column-name synonyms, first match wins.
_TITLE_COLS = ("description", "name", "text", "requirement", "title")
_PRIORITY_COLS = ("priority",)
_LAYERS_COLS = ("layers", "layer")


def _load_model():
    """Lazily import the shared requirement model (ADR-045: never bind ``lib`` at
    module import — do it at call time so cross-plugin pytest keeps its own ``lib``)."""
    shared = Path(__file__).resolve().parents[5] / "shared" / "scripts"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    from lib import requirement_model  # noqa: PLC0415

    return requirement_model


def _row_cells(line: str) -> list[str] | None:
    """Return the stripped inner cells of a markdown table row, or ``None``."""
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [c.strip() for c in s.strip("|").split("|")]


def _header_map(cells: list[str]) -> dict[str, int] | None:
    """Return a column-name→index map when ``cells`` looks like a table header."""
    low = [c.lower() for c in cells]
    if "priority" not in low:
        return None
    return {name: i for i, name in enumerate(low)}


def _pick(cells: list[str], colmap: dict[str, int] | None,
          names: tuple[str, ...], default_idx: int) -> str:
    if colmap:
        for n in names:
            idx = colmap.get(n)
            if idx is not None and idx < len(cells):
                return cells[idx]
    return cells[default_idx] if default_idx < len(cells) else ""


def _parse_layers(cell: str, rm) -> tuple:
    out: list[str] = []
    for tok in re.split(r"[,\s/|]+", cell.strip()):
        t = tok.lower()
        if rm.is_layer(t) and t not in out:
            out.append(t)
    return tuple(out)


def _infer_layers(title: str) -> tuple[tuple, str]:
    low = title.lower()
    words = set(re.findall(r"[a-z]+", low))
    if words & _UI_FLOW_WORDS or any(p in low for p in _UI_FLOW_PHRASES):
        return ("e2e",), "inferred_legacy"
    return ("unit",), "defaulted_legacy"


def parse_requirements(content: str, *, namespace: str, spec_path: str) -> list:
    """Parse every FR row (active + removed) into ``Requirement`` objects."""
    rm = _load_model()
    reqs: list = []
    colmap: dict[str, int] | None = None
    in_removed = False
    removed_level = 0

    for line in content.splitlines():
        heading = _MD_HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            if heading.group(2).strip().lower().startswith("removed requirements"):
                in_removed, removed_level = True, level
            elif in_removed and level <= removed_level:
                in_removed = False
            continue

        cells = _row_cells(line)
        if not cells or len(cells) < 3:
            continue
        header = _header_map(cells)
        if header is not None and not rm.is_canonical_fr(cells[0]):
            colmap = header
            continue
        fr_id = cells[0]
        if not rm.is_canonical_fr(fr_id):
            continue

        title = _pick(cells, colmap, _TITLE_COLS, 1)
        priority = _pick(cells, colmap, _PRIORITY_COLS, 2)
        if priority not in rm.PRIORITIES:
            priority = "Must"
        if colmap is not None:
            # A header exists: read Layers ONLY if the header names it, so the
            # adopt 5-col Description cell is never mistaken for layers.
            has_layers = any(n in colmap for n in _LAYERS_COLS)
            layers_cell = _pick(cells, colmap, _LAYERS_COLS, len(cells)) if has_layers else ""
        else:
            # No header: fall back to the positional 4-col traceability shape.
            layers_cell = cells[3] if len(cells) >= 4 else ""
        layers = _parse_layers(layers_cell, rm)
        if layers:
            source = "explicit"
        else:
            layers, source = _infer_layers(title)

        reqs.append(rm.Requirement(
            id=fr_id, namespace=namespace, spec_path=spec_path, title=title,
            priority=priority, status="removed" if in_removed else "active",
            required_layers=layers, required_layers_source=source,
        ))
    return reqs


__all__ = ["parse_requirements"]

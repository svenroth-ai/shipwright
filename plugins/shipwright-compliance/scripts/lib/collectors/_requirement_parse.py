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
* present + an ``(inferred)`` marker (adopt-generated, surface-derived — not
  author-chosen) → ``inferred_legacy`` so an adopted brownfield FR stays advisory
  (Spec §9), never collapsing into the ``explicit`` hard-gate regime
* present (explicitly headed) + non-empty but ZERO valid canonical layers, no marker
  (author typo/synonym, e.g. ``int, db``) → kept ``explicit`` + recorded in the
  ``invalid_layers`` out-accumulator; NOT demoted to legacy (that would escape the
  post-rollout hard gate and silently discard the author's intent — §11-R4 collapse)
* absent/empty + a UI/flow signal in the title → ``inferred_legacy`` → ``(e2e,)``
* absent/empty + no signal → ``defaulted_legacy`` → ``(unit,)`` (every FR ⇒ unit)

Rows under a ``## Removed Requirements`` heading are parsed with ``status="removed"``
(their tagged tests become orphans, never live coverage).
"""

from __future__ import annotations

import re

from ._lib_loader import load_shared_lib

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

# An adopt-generated Layers cell carries the EXACT `(inferred)` marker (the only
# token `artifact_writer` ever emits): its layers were derived from the detected
# surface, not author-chosen, so it reads as advisory (`inferred_legacy`) rather
# than `explicit` — else a brownfield repo's FRs collapse into the hard-gate regime
# and drown in MISSING findings (Spec §9 / R4). Matched NARROWLY to `(inferred)`
# only: a post-rollout author writing e.g. `unit, e2e (auto)` must NOT be silently
# downgraded out of the hard gate — a plain author cell carries no marker → `explicit`.
_INFERRED_MARKER_RE = re.compile(r"\(\s*inferred\s*\)", re.IGNORECASE)


def _load_model():
    """Import the shared requirement model via the robust shared-lib loader (ADR-045:
    safe even when ``sys.modules['lib']`` is already the compliance-local lib)."""
    return load_shared_lib("requirement_model")


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


def parse_requirements(
    content: str, *, spec_path: str,
    invalid_layers: list | None = None,
) -> list:
    """Parse every FR row (active + removed) into ``Requirement`` objects.

    There is no ``namespace`` argument (manifest schema v3): the manifest-key
    namespace derives from each row's own FR id, so a caller can no longer hand in
    a directory name. Every row reaching the constructor has already passed
    ``is_canonical_fr``, which is what makes that derivation total.

    ``invalid_layers`` (optional out-accumulator) collects diagnostics for FR rows
    whose **explicitly-headed** ``Layers`` cell is non-empty but resolves to ZERO
    valid canonical layers (an author typo/synonym, e.g. ``int, db``). Such a cell
    is kept ``explicit`` (so the post-rollout hard gate still fires) and its raw text
    is recorded — it is NOT demoted to advisory legacy, which would both hide it from
    the gate and silently discard the author's intent (mirror of TT1 ``invalid_tags``).
    """
    rm = _load_model()
    # Lines inside a ``## FR-Fold-Map`` section are ALIAS records, not requirements.
    # Skipping them is load-bearing, not cosmetic: webui's fold table only avoids being
    # parsed as 37 live FRs because its ids happen to be backticked. An author writing
    # the same table unbackticked would resurrect every folded id as an active
    # requirement demanding its own coverage — a large, baffling false-red.
    fold_lines = load_shared_lib("fr_fold_map").fold_map_line_numbers(content)
    reqs: list = []
    colmap: dict[str, int] | None = None
    in_removed = False
    removed_level = 0

    for lineno, line in enumerate(content.splitlines()):
        if lineno in fold_lines:
            continue
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
            layers_from_named_col = has_layers
        else:
            # No header: fall back to the positional 4-col traceability shape. This
            # cell is AMBIGUOUS (in a headerless adopt row cells[3] is the Description),
            # so a non-canonical value here is NOT treated as an invalid Layers typo.
            layers_cell = cells[3] if len(cells) >= 4 else ""
            layers_from_named_col = False
        raw_cell = layers_cell.strip()
        has_marker = bool(_INFERRED_MARKER_RE.search(layers_cell))
        layers = _parse_layers(layers_cell, rm)
        if layers:
            source = "inferred_legacy" if has_marker else "explicit"
        elif has_marker:
            # adopt-inferred cell that resolved to no valid layers → still advisory.
            source = "inferred_legacy"
        elif raw_cell and layers_from_named_col:
            # A non-empty, explicitly-headed Layers cell with zero valid canonical
            # tokens (author typo/synonym) → keep `explicit` so D-layer's post-rollout
            # hard gate still fires, and record the raw for a diagnostic. Do NOT demote
            # to legacy (that is the §11-R4 collapse: an escape + silent intent loss).
            source = "explicit"
            if invalid_layers is not None:
                invalid_layers.append({
                    "fr": fr_id, "spec_path": spec_path,
                    "raw": raw_cell, "reason": "no_canonical_layer",
                })
        else:
            # Empty cell (or an ambiguous positional cell) → legacy inference.
            layers, source = _infer_layers(title)

        reqs.append(rm.Requirement(
            id=fr_id, spec_path=spec_path, title=title,
            priority=priority, status="removed" if in_removed else "active",
            required_layers=layers, required_layers_source=source,
        ))
    return reqs


__all__ = ["parse_requirements"]

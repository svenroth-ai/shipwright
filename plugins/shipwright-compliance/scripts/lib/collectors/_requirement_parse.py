"""Parse a ``spec.md`` FR table into the frozen ``requirement_model.Requirement``.

Traceability campaign TT1. The one versioned requirement model
(``shared/scripts/lib/requirement_model.py``, R5) is the shape every traceability
consumer shares; this is the compliance-side parser that *builds* those objects
from a spec.md. It does not fork the model — it constructs it.

**Rows come from ``lib.fr_table_reader``** (campaign S4) — this module no longer
reads markdown at all. What is left here is the part that is genuinely
compliance's: turning a row's raw ``Layers`` cell into a ``required_layers``
tuple plus its provenance. The table mechanics (which column is the body, what a
header row is, what an escaped pipe means) were five inconsistent answers across
five parsers and are now one.

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

# UI/flow words → a bare FR (no Layers column) is inferred to require e2e. Matched
# on whole words (not substrings) so "view" never fires on "review"/"overview".
_UI_FLOW_WORDS: frozenset[str] = frozenset({
    "dashboard", "page", "pages", "screen", "screens", "view", "views", "button",
    "buttons", "click", "clicks", "display", "displays", "show", "shows", "render",
    "renders", "navigate", "login", "logout", "modal", "menu", "banner", "form",
    "clipboard", "widget", "scroll", "upload", "download", "toast", "wizard",
})
_UI_FLOW_PHRASES: tuple[str, ...] = ("sign in", "sign-in", "log in")

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
    invalid_ids: list | None = None,
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
    reqs: list = []

    # Rows the reader declined. Recorded rather than silently dropped: the
    # sharpest case is `generate_adoption_artifacts` emitting `FR-01.{i:02d}`
    # with no cap on i, so an adopted repo with >99 detected routes emits
    # `FR-01.100` — accepted by the pre-S4 loose regex, rejected by the
    # canonical tier, and invisible in the RTM without this.
    rejects: list = []
    for row in load_shared_lib("fr_table_reader").read_fr_rows(
        content, rejects=rejects,
    ):
        fr_id, title = row.id, row.text
        layers_cell = row.layers_cell
        layers_from_named_col = row.layers_from_named_col
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
            priority=row.priority, status=row.status,
            required_layers=layers, required_layers_source=source,
        ))

    if invalid_ids is not None:
        invalid_ids.extend(
            {"fr": r["id"], "spec_path": spec_path,
             "raw": r["raw"], "reason": r["reason"]}
            for r in rejects
        )
    return reqs


__all__ = ["parse_requirements"]

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
* present + a GLUED marker (``unit,e2e(inferred)``) → provenance is correct
  (advisory — the cell IS tool-derived) but a layer was swallowed by the missing
  space, so the loss is recorded in ``invalid_layers`` with reason
  ``marker_glued``. Detected differentially, by re-parsing with the marker split
  off and comparing; equal means it was already separated.

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

# A machine-emitted Layers cell carries the EXACT `(inferred)` marker: its layers
# were derived from the detected surface, not author-chosen, so it reads as
# advisory (`inferred_legacy`) rather than `explicit` — else a brownfield repo's
# FRs collapse into the hard-gate regime and drown in MISSING findings (Spec §9 /
# R4). Matched NARROWLY: a post-rollout author writing e.g. `unit, e2e (auto)`
# must NOT be silently downgraded out of the hard gate — a plain author cell
# carries no marker → `explicit`.
#
# **Imported, not re-declared** (campaign S5). This regex used to be a private
# copy here while `artifact_writer` hand-formatted the matching string at the
# other end, so producer and consumer each owned half of one serialized-format
# contract with nothing holding them together — the ADR-024 defect class. The
# marker and the renderer that emits it now live in `fr_table_shape`, and this
# side reads it from there.
def _marker_re():
    return load_shared_lib("fr_table_shape").INFERRED_MARKER_RE


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
    marker_re = _marker_re()
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
        has_marker = bool(marker_re.search(layers_cell))
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

        # A GLUED marker — `unit,e2e(inferred)` — is prevented at the producer
        # (`fr_table_shape.render_layers` is the only sanctioned writer) but a
        # spec.md is hand-edited by design and the iterate ADD path writes rows
        # by hand, so sanction is not enforcement. The tokeniser splits on
        # `[,\s/|]+`, so the glued token `e2e(inferred)` is not a layer and the
        # requirement silently loses e2e while still LOOKING healthy: it keeps
        # advisory provenance and, before this, recorded nothing anywhere.
        #
        # Detected differentially: parse the cell again with the marker split
        # OFF, and compare. Equal means the marker was already separated;
        # different means gluing swallowed a layer. That is exact — it needs no
        # second opinion about what a layer name may contain — and it is silent
        # on the legitimate bare-marker cell, where both sides parse to ().
        #
        # Provenance is deliberately NOT changed: the cell IS tool-derived and
        # advisory is the right regime for it. Only the loss becomes visible.
        if has_marker and invalid_layers is not None:
            body = marker_re.sub(" ", layers_cell)
            if (unglued := _parse_layers(body, rm)) != layers:
                invalid_layers.append({
                    "fr": fr_id, "spec_path": spec_path,
                    "raw": raw_cell, "reason": "marker_glued",
                    "lost": [lyr for lyr in unglued if lyr not in layers],
                })
            else:
                # A marked cell whose tokens are not layer names at all —
                # `ui (inferred)`, `ui, db (inferred)`. The marker keeps it
                # advisory (correct: it IS tool-derived) and the tokens resolve
                # to nothing, so the requirement quietly ends up with NO
                # coverage obligation and, before this, no diagnostic either —
                # the same silent-loss class as the glued marker, reached by a
                # different route. The differential above cannot see it because
                # both sides parse to the same empty tuple.
                unknown = [t for t in re.split(r"[,\s/|]+", body.strip())
                           if t and not rm.is_layer(t.lower())]
                # Only when the cell resolved to NOTHING. **This is a deliberate
                # trade-off with a real cost, not a free win.**
                #
                # It buys: no wrong-cause message on `unit and e2e (inferred)`,
                # which parses correctly to ("unit","e2e") — the stray "and" is
                # prose, and reporting it as a lost layer is exactly the
                # defect class this diagnostic exists to remove.
                #
                # It costs: a typo'd layer name ALONGSIDE a valid one is now
                # silent. `unit, e2ee (inferred)` yields ("unit",), the glued
                # differential sees nothing (both sides agree), and the dropped
                # `e2ee` is reported nowhere — the requirement quietly carries
                # one layer instead of two. Without the guard that case WAS
                # reported.
                #
                # A token in this position is either prose or a misspelling and
                # nothing about its shape distinguishes them, so one of the two
                # errors is unavoidable; silence on a partial cell was chosen
                # over a false report on every correct one. Pinned as a
                # characterization test (`test_a_typod_layer_beside_a_valid_one_
                # is_not_reported`) so the blind spot is a recorded decision.
                if not layers and unknown:
                    invalid_layers.append({
                        "fr": fr_id, "spec_path": spec_path,
                        "raw": raw_cell, "reason": "unknown_layer_token",
                        "lost": unknown,
                    })

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

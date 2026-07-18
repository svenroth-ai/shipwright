"""Value types + closed vocabulary for the ``## FR-Fold-Map`` contract (see ``fr_fold_map``).

Split out when the fold semantics grew past the ADR-096 300-LOC cap. The seam is the
usual one for this contract family: the DATA a fold-map is made of lives here (defect
kinds, the defect/map/resolution records and their serialization), while the BEHAVIOUR
that produces and consumes it — parse, merge, resolve, audit — lives next door. Nothing
here imports the behaviour, so there is no cycle and both halves stay independently
readable. Every name is re-exported from ``fr_fold_map``; import from there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

try:  # flat import off shared/scripts/lib on sys.path (tool + tests).
    from _fr_fold_map_parse import bound_raw
except ImportError:  # loaded as a package (lib._fr_fold_map_types).
    from ._fr_fold_map_parse import bound_raw  # type: ignore

# Chain length beyond which traversal stops. The visited-set in ``resolve_fold`` is what
# GUARANTEES termination (the edge set is finite); this cap is a cheap backstop bounding
# the work a pathological hand-written map can cause, set far above any real fold depth.
MAX_FOLD_DEPTH = 32

# Closed vocabulary of fold-map hygiene defects. Pinned by a drift-guard test so a new
# kind must be declared here before it can reach a consumer's renderer.
FOLD_DEFECT_KINDS = frozenset({
    "unparsable_row",          # a row that means to be an edge but has a malformed id
    "self_fold",               # FR-X → FR-X
    "conflicting_survivor",    # the same id folded to two different survivors
    "cycle",                   # the edge set contains a loop (reported once per map)
    "folded_id_still_active",  # the folded id is ALSO a live FR row (spec self-contradicts)
    "folded_id_removed",       # the folded id ALSO sits under ## Removed Requirements
    "dangling_survivor",       # survivor is in no FR table at all
    "removed_survivor",        # survivor sits under ## Removed Requirements
})

# RETIREMENT BEATS FOLDING (fail-closed). An id under ``## Removed Requirements`` is a
# deliberate, recorded decision that the requirement is GONE — so a tag on it is never
# fold-rescued, and callers must refuse the rescue rather than credit the survivor.
#
# Without this, removing an FR *and* adding one fold row in the same commit would flip the
# F11 removal gate green: a test still carrying the dead tag would be filed as a link on
# the survivor, and `_layer_coverage_removal._classify_at_head` would read that as
# "retargeted to a live FR" — repealing its own load-bearing invariant that a clean
# retarget REPLACES a dead tag rather than merely supplementing it. A two-line markdown
# edit must not be able to dismiss the tests of a removed feature.
#
# Genuine folds are unaffected: the real pattern (webui #287) drops a folded id from the FR
# table ENTIRELY and records it only here, so it is absent rather than removed, and the
# rescue applies. An id that is both removed AND folded is a spec contradiction, reported
# as ``folded_id_removed`` so the author sees why their fold row is inert.


@dataclass(frozen=True)
class FoldDefect:
    """One fold-map hygiene problem, typed so consumers render it without parsing prose."""

    kind: str
    folded: str
    survivor: str | None = None
    spec_path: str = ""
    line_no: int = 0
    raw: str = ""

    def as_dict(self) -> dict:
        """Structured form for the manifest — codes and ids first, raw text last."""
        out: dict = {"kind": self.kind, "folded": self.folded}
        if self.survivor:
            out["survivor"] = self.survivor
        if self.spec_path:
            out["spec_path"] = self.spec_path
        if self.line_no:
            out["line"] = self.line_no
        if self.raw:
            out["raw"] = bound_raw(self.raw)
        return out

    def sort_key(self) -> tuple:
        return (self.kind, self.folded, self.survivor or "", self.spec_path, self.line_no)


@dataclass(frozen=True)
class FoldMap:
    """The parsed alias table: ``folded id → direct survivor`` plus its defects."""

    edges: Mapping[str, str] = field(default_factory=dict)
    defects: tuple[FoldDefect, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.edges)


@dataclass(frozen=True)
class FoldResolution:
    """Outcome of resolving one tagged id.

    ``survivor`` is the id coverage should be filed against, or ``None`` when the tag
    could not be rescued (the caller then keeps its existing orphan behaviour, unchanged).
    ``folded`` is True only when the map was actually used, so the caller can record
    provenance. ``reason`` is ``""`` on success, else ``not_folded`` | ``cycle`` |
    ``depth_exceeded`` | ``unresolved``.

    ``terminal`` is the last id the walk reached. It is what makes an UNRESOLVED outcome
    diagnosable: a chain that ends at a retired FR must be reported as ``fr_removed``, not
    ``fr_absent`` — the tagged id itself is absent either way, so without the terminal the
    caller cannot tell "the survivor was retired" from "this id never existed".
    """

    survivor: str | None
    via: tuple[str, ...] = ()
    folded: bool = False
    reason: str = ""
    terminal: str | None = None


def sorted_defects(defects: Iterable[FoldDefect]) -> tuple[FoldDefect, ...]:
    """Deterministic order so the generated artifact is byte-stable across runs."""
    return tuple(sorted(defects, key=lambda d: d.sort_key()))


__all__ = [
    "FOLD_DEFECT_KINDS", "MAX_FOLD_DEPTH", "FoldDefect", "FoldMap", "FoldResolution",
    "sorted_defects",
]

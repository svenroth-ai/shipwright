"""The frozen ``## FR-Fold-Map`` alias-table contract (spec → folded-FR resolution).

A spec clean-up may **fold** a fine-grained FR into the broader capability FR that now
owns it (``FR-01.44`` "terminal appearance" → ``FR-01.28`` "embedded terminal"). The
folded id is never retired — it is recorded in a ``## FR-Fold-Map`` table so every
historical reference (source comments, event log, changelog, and crucially a test's
``@FR`` tag) still resolves.

Without this, a tag on a folded id reads as pointing at a requirement that does not
exist → ``fr_absent`` → ``confirmed_orphan`` → the D-orphan audit FAILs. That made two
independent good practices mutually exclusive: keeping test tags fine-grained, and
periodically raising a spec to capability altitude. (Observed for real: shipwright-webui
#287 folded 66 FRs into 29; the traceability retrofit then produced 419 orphans.)

This is the ONE parser/resolver both consumers share — the compliance ``test_links``
collector (via ``load_shared_lib``) and the shared backfill engine (flat import) — so
the two can never drift, mirroring ``fr_tag_grammar`` / ``requirement_model``. Markdown
mechanics live in ``_fr_fold_map_parse``; this module is fold *semantics* only.

THE SAFETY PROPERTY (the whole design rests on it): **fold resolution is a FALLBACK,
never an override.** :func:`resolve_fold` returns the id unchanged whenever it names a
live active FR, *without consulting the map at all*. The fold-map can therefore only
ever rescue a tag that would otherwise orphan; it can never redirect a tag away from a
requirement that is actually alive. Every ambiguous, circular, dangling or dead edge
fails **CLOSED** — the tag keeps its orphan status and a typed defect is recorded, so a
broken alias table is loud rather than silently under-resolving.

A chain is walked to the **first ACTIVE id it reaches**, passing straight through
intermediates that are removed or absent: ``A → B → C`` with ``B`` removed and ``C``
active resolves to ``C``. Stopping at the first *active* id (rather than at the chain's
literal end) is Rule 1 applied at every hop — coverage belongs to the living requirement
nearest the tag. An active id that *also* carries an outgoing fold edge is a spec
self-contradiction, reported as ``folded_id_still_active``; the live row still wins.
When the walk rescues nothing, the id it stopped at is returned as ``terminal`` so the
caller can say *why* (a removed survivor is ``fr_removed``, not ``fr_absent``). Both
consumers call :func:`resolve_fold`, so none of this can diverge between them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping

try:  # flat import off shared/scripts/lib on sys.path (tool + tests).
    from _fr_fold_map_parse import (
        bound_raw, fold_map_line_numbers, has_fold_map_section, is_canonical_fr,
        iter_fold_rows,
    )
except ImportError:  # loaded as a package (lib.fr_fold_map), e.g. via load_shared_lib.
    from ._fr_fold_map_parse import (  # type: ignore
        bound_raw, fold_map_line_numbers, has_fold_map_section, is_canonical_fr,
        iter_fold_rows,
    )

# Chain length beyond which traversal stops. The visited-set below is what GUARANTEES
# termination (the edge set is finite); this cap is a cheap backstop bounding the work a
# pathological hand-written map can cause, and is set far above any real fold depth.
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


def _sorted_defects(defects: Iterable[FoldDefect]) -> tuple[FoldDefect, ...]:
    """Deterministic order so the generated artifact is byte-stable across runs."""
    return tuple(sorted(defects, key=lambda d: d.sort_key()))


def parse_fold_map(spec_text: str, *, spec_path: str = "") -> FoldMap:
    """Parse one spec's ``## FR-Fold-Map`` table(s). Never raises on malformed input.

    A duplicate row for the same folded id is handled exactly like a cross-spec conflict:
    identical survivor → one effective edge; DIFFERENT survivor → the edge is dropped and
    a ``conflicting_survivor`` defect recorded. Last-write-wins would silently pick a
    winner from a copy-paste or merge-conflict artifact.
    """
    edges: dict[str, str] = {}
    defects: list[FoldDefect] = []
    conflicted: set[str] = set()
    for row in iter_fold_rows(spec_text or ""):
        folded, survivor = row.folded, row.survivor
        if not (is_canonical_fr(folded) and is_canonical_fr(survivor)):
            defects.append(FoldDefect(
                kind="unparsable_row", folded=folded or "?", survivor=survivor or None,
                spec_path=spec_path, line_no=row.line_no, raw=row.raw))
            continue
        if folded == survivor:
            defects.append(FoldDefect(
                kind="self_fold", folded=folded, survivor=survivor,
                spec_path=spec_path, line_no=row.line_no))
            continue
        prior = edges.get(folded)
        if prior is not None and prior != survivor:
            conflicted.add(folded)
            defects.append(FoldDefect(
                kind="conflicting_survivor", folded=folded, survivor=survivor,
                spec_path=spec_path, line_no=row.line_no, raw=f"{prior} vs {survivor}"))
            continue
        edges[folded] = survivor
    for folded in conflicted:
        edges.pop(folded, None)
    return FoldMap(edges=edges, defects=_sorted_defects(defects))


def merge_fold_maps(maps: Iterable[FoldMap]) -> FoldMap:
    """Union several specs' maps into the one map in force across the repo.

    A folded id claimed by two DIFFERENT survivors is ambiguous, so the edge is
    **dropped** (fail-closed — never guess a winner) and a ``conflicting_survivor``
    defect recorded. A duplicate identical edge is simply one effective edge.
    """
    edges: dict[str, str] = {}
    defects: list[FoldDefect] = []
    # Collect the full claimed-survivor SET per folded id before judging. Reporting as we
    # go made the defect's content depend on spec discovery order (which of the two rivals
    # landed in `survivor` / `raw`), and emitted one defect per extra claimant instead of
    # one per conflicted id — so the same repo could render different manifest bytes.
    claims: dict[str, set[str]] = {}
    for fold_map in maps:
        defects.extend(fold_map.defects)
        for folded in sorted(fold_map.edges):
            claims.setdefault(folded, set()).add(fold_map.edges[folded])
    for folded in sorted(claims):
        survivors = sorted(claims[folded])
        if len(survivors) == 1:
            edges[folded] = survivors[0]
            continue
        defects.append(FoldDefect(
            kind="conflicting_survivor", folded=folded, survivor=survivors[0],
            raw=" vs ".join(survivors)))
    return FoldMap(edges=edges, defects=_sorted_defects(defects))


def resolve_fold(
    fold_map: FoldMap, fr_id: str, *, is_active: Callable[[str], bool],
) -> FoldResolution:
    """Resolve a tagged id to the FR its coverage should be filed against.

    Rule 1 (the safety property) — an id naming a LIVE active FR resolves to itself and
    the map is NEVER consulted, so a live requirement can never be redirected away and an
    id that is both active and folded keeps its own independent coverage obligation.
    Rule 2 — otherwise walk the map to the first ACTIVE id the chain reaches, passing
    through inactive/removed intermediates. Rule 3 — anything else (cycle, over-deep
    chain, dangling or dead terminal, id absent from the map) returns ``survivor=None``,
    leaving the caller's existing orphan behaviour untouched.
    """
    if is_active(fr_id):
        return FoldResolution(survivor=fr_id, via=(), folded=False)
    if not fold_map.edges or fr_id not in fold_map.edges:
        return FoldResolution(survivor=None, folded=False, reason="not_folded")

    chain = [fr_id]
    seen = {fr_id}
    cur = fr_id
    for _ in range(MAX_FOLD_DEPTH):
        nxt = fold_map.edges.get(cur)
        if nxt is None:
            return FoldResolution(None, tuple(chain), False, "unresolved", cur)
        if nxt in seen:
            return FoldResolution(None, tuple(chain), False, "cycle", cur)
        chain.append(nxt)
        seen.add(nxt)
        if is_active(nxt):
            return FoldResolution(nxt, tuple(chain), True, "", nxt)
        cur = nxt
    return FoldResolution(None, tuple(chain), False, "depth_exceeded", cur)


def _cycle_defects(fold_map: FoldMap) -> tuple[list[FoldDefect], set[str]]:
    """``(defects, members)`` — cycles reported ONCE PER CYCLE, plus every looped id.

    Emitting per resolution attempt would amplify a single broken edge into one
    diagnostic per tag referencing it; the defect is a property of the map, so it is
    detected structurally here. The cycle is named by its smallest member id so the same
    loop yields one stable, deterministic entry regardless of traversal entry point.

    ``members`` lets the caller suppress the per-edge SURVIVOR complaints a cycle would
    otherwise spawn: a looped edge can never reach an active id, so each one would ALSO
    report ``dangling_survivor`` — one root cause rendered as N+1 defects, burying the
    actionable one. Detection is purely structural over ``edges`` and says nothing about
    whether a member is active or removed, so the caller must still emit the
    folded-id-status diagnostics for looped ids itself.
    """
    out: list[FoldDefect] = []
    reported: set[frozenset[str]] = set()
    members: set[str] = set()
    for start in sorted(fold_map.edges):
        seen: list[str] = []
        cur: str | None = start
        while cur is not None and cur not in seen:
            seen.append(cur)
            cur = fold_map.edges.get(cur)
        if cur is None:
            continue
        loop = frozenset(seen[seen.index(cur):])
        members |= loop
        if loop in reported:
            continue
        reported.add(loop)
        ordered = sorted(loop)
        out.append(FoldDefect(kind="cycle", folded=ordered[0],
                              survivor=fold_map.edges.get(ordered[0]),
                              raw=" → ".join(ordered)))
    return out, members


def audit_fold_map(
    fold_map: FoldMap, *, active_ids: set[str], removed_ids: set[str],
) -> tuple[FoldDefect, ...]:
    """Hygiene checks needing the FR table (plus structural cycle detection).

    Deterministically ordered. Note ``folded_id_still_active`` is reported but does NOT
    change resolution: per Rule 1 the live row wins and keeps its own coverage
    obligation — the fold entry for it is inert.
    """
    out, in_cycle = _cycle_defects(fold_map)
    is_active = lambda fr: fr in active_ids  # noqa: E731 — one-expression predicate
    for folded in sorted(fold_map.edges):
        # The spec-contradiction diagnostics are emitted BEFORE the cycle skip: they are
        # about the folded id's own status, not about where its edge leads, so a loop
        # elsewhere in the map must not swallow them.
        if folded in active_ids:
            out.append(FoldDefect(kind="folded_id_still_active", folded=folded,
                                  survivor=fold_map.edges[folded]))
        elif folded in removed_ids:
            out.append(FoldDefect(kind="folded_id_removed", folded=folded,
                                  survivor=fold_map.edges[folded]))
        if folded in in_cycle:
            continue  # the cycle defect already names this edge — do not double-report
        # Judge the CHAIN, not this edge's immediate target. `A → B → C` with B absent and
        # C active resolves perfectly at runtime; complaining that B is "dangling" would
        # put a defect in the manifest — and fail D-orphan at LOW — for a healthy fold.
        res = resolve_fold(fold_map, folded, is_active=is_active)
        if res.survivor:
            continue
        terminal = res.terminal or fold_map.edges[folded]
        kind = "removed_survivor" if terminal in removed_ids else "dangling_survivor"
        out.append(FoldDefect(kind=kind, folded=folded, survivor=terminal))
    return _sorted_defects(out)


__all__ = [
    "MAX_FOLD_DEPTH", "FOLD_DEFECT_KINDS", "FoldDefect", "FoldMap", "FoldResolution",
    "parse_fold_map", "merge_fold_maps", "resolve_fold", "audit_fold_map",
    # Re-exported so an FR-table parser needs only THIS module to learn which lines
    # belong to a fold-map section and must not be read as requirement rows.
    "fold_map_line_numbers", "has_fold_map_section",
]

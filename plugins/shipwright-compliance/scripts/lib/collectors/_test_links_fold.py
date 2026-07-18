"""``## FR-Fold-Map`` wiring for the ``test_links`` collector.

Split from ``test_links`` so that file stays under its ADR-096 cap and the fold concern
is inspectable on its own. The fold *contract* (parse / merge / resolve / audit) is the
shared ``lib.fr_fold_map`` — nothing is re-implemented here; this module only adapts it
to the collector's requirement index.

THE SAFETY PROPERTY, restated where it is applied: :func:`resolve_binding` is consulted
ONLY for a tag that found no active requirement. A tag naming a live FR never reaches
this module, so the fold-map can rescue an orphan but can never redirect live coverage.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._lib_loader import load_shared_lib


def load_fold():
    """Import the frozen fold-map contract via the ADR-045-safe shared-lib loader."""
    return load_shared_lib("fr_fold_map")


@dataclass(frozen=True)
class FoldContext:
    """The merged fold-map in force across every spec, plus its hygiene defects."""

    fold_map: object
    defects: tuple
    active_ids: frozenset

    @property
    def edges(self) -> dict:
        return dict(getattr(self.fold_map, "edges", {}) or {})

    def as_manifest_fields(self) -> dict:
        """The optional manifest keys — **omitted entirely when empty**.

        A repo with no fold-map (the common case, including this monorepo) must emit a
        byte-identical manifest to before this feature existed: no empty ``fold_map: {}``
        churning a committed artifact, no schema surface for consumers to trip on.
        """
        out: dict = {}
        if self.edges:
            out["fold_map"] = dict(sorted(self.edges.items()))
        if self.defects:
            out["fold_defects"] = [d.as_dict() for d in self.defects]
        return out


def build_fold_context(
    spec_entries: list[tuple[str, str]], by_display_id: dict,
) -> FoldContext:
    """Parse + merge every spec's fold-map and audit it against the FR index.

    ``spec_entries`` is ``[(spec_text, rel_spec_path), …]``; ``by_display_id`` maps a
    display FR id to its parsed ``Requirement`` objects.
    """
    fold = load_fold()
    merged = fold.merge_fold_maps([
        fold.parse_fold_map(text, spec_path=rel) for text, rel in spec_entries
    ])
    active_ids = frozenset(
        d for d, reqs in by_display_id.items() if any(r.is_active for r in reqs))
    removed_ids = {d for d in by_display_id if d not in active_ids}
    # BOTH halves: `merged.defects` are the parse/merge-time problems (self-fold,
    # unparsable row, conflicting survivor) and `audit_fold_map` adds the ones that need
    # the FR table (cycle, dangling/removed survivor, folded-id-still-active). Reporting
    # only the latter would silently drop a whole class of broken alias table.
    defects = tuple(merged.defects) + tuple(fold.audit_fold_map(
        merged, active_ids=set(active_ids), removed_ids=removed_ids))
    return FoldContext(fold_map=merged, defects=defects, active_ids=active_ids)


def resolve_binding(
    ctx: FoldContext, fr_id: str, by_display_id: dict,
) -> tuple[list, str, str]:
    """``(active_requirements, resolved_from, terminal)`` for a tag with no active FR.

    ``active`` empty means the map could not rescue the tag — cycle, dangling or removed
    terminal, or simply not folded — so the caller's existing orphan branch runs unchanged.
    ``resolved_from`` is the folded id the source literally carries, kept as provenance on
    the link filed against the SURVIVING requirement.

    ``terminal`` is the id the walk stopped at, returned even on failure so the caller can
    classify the orphan honestly: a chain ending at a RETIRED FR is ``fr_removed``, not
    ``fr_absent``. Without it the tagged id looks merely absent in both cases and the
    operator is told "this FR never existed" about a requirement that was deliberately
    folded away.
    """
    if not ctx.edges:
        return [], "", ""
    if by_display_id.get(fr_id):
        # The id IS in an FR table but has no active row ⇒ it sits under
        # ``## Removed Requirements``. Retirement beats folding: a recorded decision that
        # the requirement is gone is never overridden by a fold row, or removing an FR and
        # adding one alias line in the same commit would flip the F11 removal gate green
        # for tests still carrying the dead tag. Reported as ``folded_id_removed``.
        return [], "", fr_id
    res = load_fold().resolve_fold(
        ctx.fold_map, fr_id, is_active=lambda fid: fid in ctx.active_ids)
    terminal = res.terminal or ""
    if not res.survivor:
        return [], "", terminal
    active = [r for r in by_display_id.get(res.survivor, []) if r.is_active]
    return (active, fr_id, terminal) if active else ([], "", terminal)


def spec_entries(spec_files, project_root, rel) -> list[tuple[str, str]]:
    """Read each spec once as ``(text, rel_path)`` for both parsers to share."""
    return [
        (Path(s).read_text(encoding="utf-8", errors="ignore"), rel(s, project_root))
        for s in spec_files
    ]


__all__ = [
    "FoldContext", "build_fold_context", "load_fold", "resolve_binding", "spec_entries",
]

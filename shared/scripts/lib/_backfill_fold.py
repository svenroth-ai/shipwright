"""``## FR-Fold-Map`` leg for the backfill engine (see ``backfill_signals``).

The mirror of the collector's ``_test_links_fold``: both consumers adapt the SHARED
``fr_fold_map`` contract to their own requirement index, and neither re-implements the
walk — that is what keeps the retrofit engine and the compliance collector from
disagreeing about what a folded tag means (pinned by a cross-consumer test).

Split from ``backfill_signals`` when fold awareness pushed it past the ADR-096 300-LOC cap.
"""

from __future__ import annotations


def _resolve_fold():
    """The shared fold resolver, imported lazily and BOTH ways (ADR-045).

    Lazy so ``fr_fold_map`` is not a load-time dependency of the signal cascade; dual-form
    so it works whether this module was imported flat (``_backfill_fold``) or as a package
    (``lib._backfill_fold``) — a flat-only import silently breaks the package path.
    """
    try:
        from fr_fold_map import resolve_fold
    except ImportError:
        from .fr_fold_map import resolve_fold  # type: ignore
    return resolve_fold


def resolve_tag(fr: str, *, active_ids, removed_ids, fold_map) -> tuple[str | None, str | None]:
    """``(survivor, terminal)`` for a tagged id. ``survivor`` None ⇒ rescues nothing.

    Order is the contract:

    1. An ACTIVE id resolves to itself — the fold-map is never consulted, so a live
       requirement can never be redirected away from its own coverage.
    2. A REMOVED id rescues nothing. Retirement beats folding: a recorded decision that
       the requirement is gone is not overridden by a fold row, or removing an FR and
       adding one alias line in the same commit would flip the F11 removal gate green for
       tests still carrying the dead tag. (See the note in ``_fr_fold_map_types``.)
    3. Otherwise walk the map to the first active id the chain reaches.

    ``terminal`` — the id the walk stopped at — lets the caller name an unrescued tag
    honestly: a chain ending at a RETIRED FR is ``fr_removed``, not ``fr_absent``.
    """
    if fr in active_ids:
        return fr, fr
    if fr in removed_ids:
        return None, fr
    if fold_map is None or not getattr(fold_map, "edges", None):
        return None, None
    res = _resolve_fold()(fold_map, fr, is_active=lambda f: f in active_ids)
    return res.survivor, res.terminal


__all__ = ["resolve_tag"]

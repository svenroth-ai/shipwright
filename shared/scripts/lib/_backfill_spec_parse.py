"""Spec.md FR-table parsing for the shared backfill engine (see ``backfill_scan``).

Extracted from ``backfill_scan`` when fold-map awareness pushed that module past the
300-LOC cap. The seam is cohesive rather than arbitrary: everything here answers "what
requirements does this spec declare?" — the ``FR`` record and the table parser that
builds it — while ``backfill_scan`` keeps filesystem/test/git discovery. Both names are
re-exported from ``backfill_scan``, so every existing import path still works.
"""

from __future__ import annotations

from dataclasses import dataclass

try:  # flat import off shared/scripts/lib on sys.path (tool + tests).
    from fr_table_reader import read_fr_rows
except ImportError:  # loaded as a package (lib._backfill_spec_parse).
    from .fr_table_reader import read_fr_rows  # type: ignore


@dataclass(frozen=True)
class FR:
    """One functional requirement as the backfill engine needs it (id/text/status)."""

    id: str
    text: str
    status: str  # "active" | "removed"


def parse_frs(spec_text: str) -> list[FR]:
    """Project a spec.md FR table onto ``FR`` records — active AND removed rows.

    Unlike ``drift_parsers.parse_fr_table`` (which drops removed rows), the backfill
    engine needs the removed set to categorise ``confirmed`` / ``possible`` orphans, so
    this keeps both with a ``status``. That projection is all this function does now:
    the markdown mechanics — including the ``## FR-Fold-Map`` skip, which is
    load-bearing rather than cosmetic — live in ``fr_table_reader`` (campaign S4).
    """
    return [
        FR(id=row.id, text=row.text, status=row.status)
        for row in read_fr_rows(spec_text)
    ]


__all__ = ["FR", "parse_frs"]

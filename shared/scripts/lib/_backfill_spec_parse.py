"""Spec.md FR-table parsing for the shared backfill engine (see ``backfill_scan``).

Extracted from ``backfill_scan`` when fold-map awareness pushed that module past the
300-LOC cap. The seam is cohesive rather than arbitrary: everything here answers "what
requirements does this spec declare?" — the ``FR`` record and the table parser that
builds it — while ``backfill_scan`` keeps filesystem/test/git discovery. Both names are
re-exported from ``backfill_scan``, so every existing import path still works.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

try:  # flat import off shared/scripts/lib on sys.path (tool + tests).
    from fr_fold_map import fold_map_line_numbers
    from requirement_model import CANONICAL_FR_RE
except ImportError:  # loaded as a package (lib._backfill_spec_parse).
    from .fr_fold_map import fold_map_line_numbers  # type: ignore
    from .requirement_model import CANONICAL_FR_RE  # type: ignore

_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
_TITLE_COLS = ("description", "name", "text", "requirement", "title")


@dataclass(frozen=True)
class FR:
    """One functional requirement as the backfill engine needs it (id/text/status)."""

    id: str
    text: str
    status: str  # "active" | "removed"


def _row_cells(line: str) -> list[str] | None:
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [c.strip() for c in s.strip("|").split("|")]


def parse_frs(spec_text: str) -> list[FR]:
    """Parse a spec.md FR table into ``FR`` records — active AND removed rows.

    Unlike ``drift_parsers.parse_fr_table`` (which drops removed rows), the backfill
    engine needs the removed set to categorise ``confirmed`` / ``possible`` orphans, so
    this loop keeps both with a ``status``.

    Rows inside a ``## FR-Fold-Map`` section are skipped: they are ALIAS records, not
    requirements. This is load-bearing, not cosmetic — webui's fold table only avoids
    being read as 37 live FRs because its ids happen to be backticked, and an author
    writing the same table unbackticked would otherwise resurrect every folded id as an
    active requirement demanding its own coverage. The twin guard lives in the
    compliance collector's ``_requirement_parse``; both defer to the one span rule in
    ``_fr_fold_map_parse`` so they cannot drift.
    """
    out: list[FR] = []
    in_removed = False
    removed_level = 0
    header: dict[str, int] | None = None
    fold_lines = fold_map_line_numbers(spec_text)
    for lineno, line in enumerate(spec_text.splitlines()):
        if lineno in fold_lines:
            continue
        h = _HEADING_RE.match(line)
        if h:
            level = len(h.group(1))
            if h.group(2).strip().lower().startswith("removed requirements"):
                in_removed, removed_level = True, level
            elif in_removed and level <= removed_level:
                in_removed = False
            continue
        cells = _row_cells(line)
        if not cells or len(cells) < 2:
            continue
        if not CANONICAL_FR_RE.match(cells[0]):
            low = [c.lower() for c in cells]
            if "priority" in low:
                header = {n: i for i, n in enumerate(low)}
            continue
        fr_id = cells[0]
        text = ""
        if header:
            for n in _TITLE_COLS:      # _TITLE_COLS never contains "priority"
                idx = header.get(n)
                if idx is not None and idx < len(cells):
                    text = cells[idx]
                    break
        if not text:
            text = cells[1] if len(cells) > 1 else ""
        out.append(FR(id=fr_id, text=text, status="removed" if in_removed else "active"))
    return out


__all__ = ["FR", "parse_frs"]

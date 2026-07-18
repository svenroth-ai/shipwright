"""Markdown mechanics for the ``## FR-Fold-Map`` alias table (see ``fr_fold_map``).

Split from ``fr_fold_map`` so each file stays under the ADR-096 300-LOC cap and the
seam is meaningful: everything here is *how markdown is read* (heading nesting, section
spans, cell decoration), while the fold *semantics* (merge, resolve, audit) live next
door. Nothing here knows what a fold means.

Section bounds are exported because the two FR-table parsers must SKIP the fold-map
span: a fold-map row is an alias record, never a live requirement. webui's table escapes
that only because its ids happen to be backticked — an unbackticked one would otherwise
resurrect every folded id as an active requirement demanding its own coverage. The span
rule is defined once, here, so the parsers cannot each re-derive it slightly differently
(the section closes at the next heading of EQUAL-OR-SHALLOWER level, so a deeper
sub-heading inside the section does not truncate it while a sibling section does).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
_CANONICAL_FR_RE = re.compile(r"^FR-\d{2}\.\d{2}$")
# "Looks like someone meant an FR id" — case/format tolerant on purpose. Used ONLY to tell
# an attempted edge row apart from a header/prose row, never to accept an id. Without it a
# row whose BOTH cells are malformed (`| FR-1.44 | FR-1.28 |`) reads as a header and is
# silently dropped — the exact silent-swallow the defect vocabulary exists to prevent.
_FR_ISH_RE = re.compile(r"^fr[\s_-]?\d", re.IGNORECASE)
_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$")
# Leading arrow glyphs the survivor column header ("→ Survivor") tends to leak into cells.
_ARROW_PREFIX_RE = re.compile(r"^(?:→|-{1,2}>|➜|»)\s*")
# Repo-controlled markdown is echoed into a JSON artifact that reporting surfaces render,
# so a raw row is kept only where it is genuinely needed to fix the spec, and bounded.
MAX_RAW_LEN = 160


def normalise_heading(text: str) -> str:
    """``## FR-Fold-Map`` / ``### FR Fold Map`` / ``## fr-fold-map`` → ``frfoldmap``."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def is_canonical_fr(fr_id: str) -> bool:
    """Match the FROZEN canonical form exactly — case-SENSITIVE, deliberately.

    The ``@FR`` tag grammar and the FR-table parser are both case-sensitive, so accepting
    ``fr-01.44`` here would let the fold-map resolve ids that no tag or table row can ever
    produce. A lowercase entry therefore fails to parse and is reported as an
    ``unparsable_row`` defect — loud and fixable — rather than silently normalised into a
    third dialect of what counts as an FR id.
    """
    return bool(_CANONICAL_FR_RE.match(fr_id))


def looks_like_fr(cell: str) -> bool:
    """Loose "this cell was MEANT to be an FR id" test — never an acceptance check.

    Lets a row with two malformed ids still be recognised as an attempted edge (and so
    reported as ``unparsable_row``) while a header cell like ``Folded ID`` or
    ``→ Survivor`` is correctly ignored.
    """
    return bool(_FR_ISH_RE.match(cell.strip()))


def clean_cell(cell: str) -> str:
    """Strip the decoration an author may wrap an id in: backticks, bold, arrows."""
    s = cell.strip().strip("*").strip()
    s = _ARROW_PREFIX_RE.sub("", s)
    s = s.replace("`", "").strip()
    return _ARROW_PREFIX_RE.sub("", s).strip()


def row_cells(line: str) -> list[str] | None:
    """The stripped inner cells of a markdown table row, or ``None``."""
    s = line.strip()
    if not s.startswith("|"):
        return None
    return [c.strip() for c in s.strip("|").split("|")]


def bound_raw(text: str) -> str:
    """Bound + flatten a raw markdown row before it enters a generated artifact."""
    flat = " ".join(text.split())
    return flat if len(flat) <= MAX_RAW_LEN else flat[: MAX_RAW_LEN - 1] + "…"


def fold_map_section_spans(spec_text: str) -> tuple[tuple[int, int], ...]:
    """Every ``## FR-Fold-Map`` section as a 0-based ``(start, end)`` line span.

    ``start`` is the heading line, ``end`` is exclusive. A tuple (not a single span)
    because a spec may legitimately carry more than one fold-map section — e.g. after a
    merge, or one per area — and a parser that skipped only the first would let the rest
    leak back into the FR table.
    """
    lines = spec_text.splitlines()
    spans: list[tuple[int, int]] = []
    start: int | None = None
    level = 0
    for i, line in enumerate(lines):
        heading = _HEADING_RE.match(line)
        if not heading:
            continue
        this_level = len(heading.group(1))
        if normalise_heading(heading.group(2)) == "frfoldmap":
            if start is not None:
                spans.append((start, i))
            start, level = i, this_level
        elif start is not None and this_level <= level:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(lines)))
    return tuple(spans)


def has_fold_map_section(spec_text: str) -> bool:
    """True when the spec declares at least one ``## FR-Fold-Map`` section."""
    return bool(fold_map_section_spans(spec_text or ""))


def fold_map_line_numbers(spec_text: str) -> frozenset[int]:
    """0-based line indices that fall inside ANY fold-map section.

    The form the FR-table parsers consume: a cheap membership test they can apply to the
    line they are about to parse, with no heading state of their own to get wrong.
    """
    return frozenset(
        i for start, end in fold_map_section_spans(spec_text or "")
        for i in range(start, end)
    )


@dataclass(frozen=True)
class FoldRow:
    """One candidate edge row, with the provenance a defect needs to be actionable."""

    folded: str          # cleaned cell 0
    survivor: str        # cleaned cell 1
    line_no: int         # 1-based, for a defect a human can jump to
    raw: str             # bounded/flattened source row


def iter_fold_rows(spec_text: str) -> Iterator[FoldRow]:
    """Yield the rows inside fold-map sections that *look like an attempted edge*.

    Header rows (``| Folded ID | → Survivor | …``), separator rows and prose yield
    nothing — neither of their first two cells cleans to anything FR-shaped — so they
    can never be mistaken for a malformed edge. A row where exactly one side parses IS
    yielded, because it meant to be an edge and its breakage must be reported.
    """
    lines = spec_text.splitlines()
    for start, end in fold_map_section_spans(spec_text or ""):
        for i in range(start, end):
            cells = row_cells(lines[i])
            if not cells or len(cells) < 2:
                continue
            if all(_SEPARATOR_CELL_RE.match(c) for c in cells if c):
                continue
            folded, survivor = clean_cell(cells[0]), clean_cell(cells[1])
            if not any(is_canonical_fr(c) or looks_like_fr(c) for c in (folded, survivor)):
                continue  # header row or prose — not an attempted edge
            yield FoldRow(folded=folded, survivor=survivor, line_no=i + 1,
                          raw=bound_raw(lines[i]))


__all__ = [
    "MAX_RAW_LEN", "FoldRow", "bound_raw", "clean_cell", "fold_map_line_numbers", "looks_like_fr",
    "fold_map_section_spans", "has_fold_map_section", "is_canonical_fr",
    "iter_fold_rows", "normalise_heading", "row_cells",
]

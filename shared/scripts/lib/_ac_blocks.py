"""Document SCANNING for the shipped FR heading+bullet shape — where a block
starts and ends, where a bullet's opening line sits, how a marker splices in.

Split out of ``ac_identity.py`` (external code review, 2026-09-06: adding
``_iter_heading_anchored_blocks`` alongside ``_iter_bullet_positions`` pushed
that module past the 300-LOC bloat-baseline threshold a second time). This
module answers "where", never "is this marker valid" (that is
``_ac_markers.py``) and never "what should mint/read do about it" (that is
``ac_identity.py``, the only importer of both).

**Scope — heading-anchored only, not every shape ``fr_criteria`` tolerates.**
``lib.fr_criteria`` (R0) also accepts a legacy bold-anchor form
(``**FR-XX.YY: Name**``); this module deliberately does not, so both
``_iter_bullet_positions`` (mint's discovery) and
``_iter_heading_anchored_blocks`` (read's discovery) agree with each other on
exactly which FR occurrences exist — using ``fr_criteria.iter_anchored_blocks``
directly for read's discovery once made it see ids mint never scans (external
code review).

**Bullet eligibility mirrors ``read()``'s adjacency gate too (external code
review, 2026-09-06, round 2).** ``read()`` extracts criterion TEXT via
``fr_criteria.block_criteria(strict=True)``, which only ever looks at a
block's CONTIGUOUS LEADING bullet run — a block whose first non-blank line
isn't itself a bullet (e.g. a nested subheading, or a prose paragraph) yields
NO criteria at all, however many bullets sit later in the block.
``_leading_bullet_run_indices`` below is an independent, narrower copy of
that same gate (``fr_criteria._leading_bullet_run``, kept private there): if
``iter_bullet_positions`` scanned every bullet in the block unconditionally,
``mint()`` could stamp a marker onto a bullet ``read()`` can never see —
the id would exist in the text but be permanently invisible to the reader
that is supposed to be its only consumer. Mirroring the gate here means a
bullet is eligible for minting if and only if ``read()`` can also see it.
"""

from __future__ import annotations

import re
from typing import Iterator

from lib._ac_markers import parse_marker

#: A heading anchor for an FR id — the shipped shape only (see module
#: docstring "Scope").
_HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<id>FR-\d+(?:\.\d+)*)\b")

#: Any heading at all, used only to find where the CURRENT FR's block ends.
_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+")

#: A criterion bullet's own OPENING line: ``-``/``*``/``+`` or ``1.``/``1)``,
#: mirroring ``fr_criteria._BULLET_RE`` (kept as an independent, narrower
#: copy on purpose — see module docstring "Scope" for why this module does
#: not reach into `fr_criteria`'s private regexes).
BULLET_RE = re.compile(r"^(?P<lead>\s*(?:[-*+]|\d+[.)])\s+)(?P<rest>\S.*)$")

_CHECKBOX_RE = re.compile(r"^\[[ xX]\]\s*")
_ASSERTION_RE = re.compile(r"^\([A-Za-z]\)\s*")

#: A single whole-line italic attribution (e.g. ``_Source: tests._``) —
#: mirrors ``fr_criteria._LEADING_ATTRIBUTION_RE`` exactly, so a block shaped
#: this way is not made ineligible for minting when ``read()`` still tolerates
#: it (the one narrow exception ``fr_criteria`` itself carves out).
_LEADING_ATTRIBUTION_RE = re.compile(r"^_[^_\n]+_\.?\s*$")


def _iter_heading_blocks_by_index(lines: list[str]) -> Iterator[tuple[str, int, int]]:
    """``(fr_id, body_start, body_end)`` as ABSOLUTE indices into ``lines`` —
    the shared core for both ``iter_bullet_positions`` (needs indices, to
    splice a marker into the line in place) and
    ``iter_heading_anchored_blocks`` (needs the sliced body). A block runs
    from just after its heading to the next heading of the SAME OR HIGHER
    rank, or the end of the document; ``i`` always advances by exactly 1
    (never jumps to a block's own end), so a NESTED FR heading still gets its
    own block too — matching ``fr_criteria.iter_anchored_blocks``'s same
    choice (see that module's docstring for why).
    """
    n = len(lines)
    i = 0
    while i < n:
        heading = _HEADING_RE.match(lines[i])
        if not heading:
            i += 1
            continue
        fr_id, level = heading.group("id"), len(heading.group(1))
        j = i + 1
        while j < n:
            any_heading = _ANY_HEADING_RE.match(lines[j])
            if any_heading and len(any_heading.group(1)) <= level:
                break
            j += 1
        yield fr_id, i + 1, j
        i += 1


def _leading_bullet_run_indices(lines: list[str], start: int, end: int) -> list[int]:
    """Absolute indices, within ``lines[start:end]``, of the bullet-OPENING
    lines belonging to the block's CONTIGUOUS LEADING bullet run — mirrors
    ``fr_criteria._leading_bullet_run`` exactly (skip blank lines; one
    italic-attribution line tolerated; the first non-blank/non-attribution
    line must itself be a bullet or the run is empty; a blank line only
    continues the run when it separates two bullets of the SAME list). See
    module docstring for why this must match ``read()``'s gate.
    """
    i = start
    while i < end and not lines[i].strip():
        i += 1
    if i < end and _LEADING_ATTRIBUTION_RE.match(lines[i].strip()):
        i += 1
        while i < end and not lines[i].strip():
            i += 1
    if i >= end or not BULLET_RE.match(lines[i]):
        return []
    positions: list[int] = []
    j = i
    while j < end:
        line = lines[j]
        if BULLET_RE.match(line):
            positions.append(j)
            j += 1
            continue
        if line.strip() and line[:1].isspace():
            j += 1  # continuation line, not its own bullet
            continue
        if not line.strip():
            k = j
            while k < end and not lines[k].strip():
                k += 1
            if k < end and BULLET_RE.match(lines[k]):
                j = k
                continue
        break
    return positions


def iter_bullet_positions(lines: list[str]) -> Iterator[tuple[str, int]]:
    """``(fr_id, line_index)`` for every criterion-bullet OPENING line in the
    CONTIGUOUS LEADING bullet run of a heading-anchored FR block, in document
    order — ``mint()``'s discovery. See module docstring "Bullet eligibility
    mirrors read()'s adjacency gate too": a block whose leading run is empty
    (e.g. a nested subheading sits between the FR heading and its bullets)
    contributes no bullets at all, exactly like ``read()``.
    """
    for fr_id, start, end in _iter_heading_blocks_by_index(lines):
        for idx in _leading_bullet_run_indices(lines, start, end):
            yield fr_id, idx


def iter_all_bullet_positions(lines: list[str]) -> Iterator[tuple[str, int]]:
    """``(fr_id, line_index)`` for EVERY criterion-bullet OPENING line
    anywhere in a heading-anchored FR block, in document order — unlike
    ``iter_bullet_positions``, NOT gated to the block's contiguous leading
    run. Used for registry SEEDING and duplicate-marker detection
    (``mint()`` pass 1), which must see every ``[ACnn]`` marker already in
    the block, not just the ones ``read()`` can also see: minting (pass 2,
    ``iter_bullet_positions``) must never stamp an id ``read()`` cannot see,
    but seeding never writes anything, so the risk runs the other way —
    missing an existing marker outside the leading run would let a
    lost/stale registry re-assign its number to a different criterion
    (external code review, 2026-09-06 round 3)."""
    for fr_id, start, end in _iter_heading_blocks_by_index(lines):
        for idx in range(start, end):
            if BULLET_RE.match(lines[idx]):
                yield fr_id, idx


def iter_heading_anchored_blocks(content: str) -> Iterator[tuple[str, list[str]]]:
    """``(fr_id, block_lines)`` for every HEADING-anchored FR block, in
    document order — ``read()``'s discovery. Termination mirrors
    ``iter_bullet_positions``: same-or-higher-rank heading, or end of
    document. Criterion EXTRACTION from each block still delegates to
    ``fr_criteria.block_criteria`` — only block DISCOVERY is independent.

    Splits on ``"\\n"`` exactly like ``mint()``'s own line list, NOT
    ``str.splitlines()`` (external code review, 2026-09-06 round 2):
    ``splitlines()`` also breaks on ``\\r``, ``\\v``, ``\\f`` and U+2028,
    which ``mint()`` does not treat as line boundaries — an exotic document
    containing one of those would otherwise make the two halves discover
    DIFFERENT block boundaries for the same content.
    """
    lines = content.split("\n")
    for fr_id, start, end in _iter_heading_blocks_by_index(lines):
        yield fr_id, lines[start:end]


def embedded_ac_num(line: str, *, fr_id: str) -> int | None:
    """The number already embedded in this bullet's ``[ACnn]`` marker, or
    ``None`` when the bullet carries no marker yet. Raises
    ``MalformedAcMarkerError`` via ``parse_marker`` on a marker that cannot
    be trusted."""
    bullet = BULLET_RE.match(line)
    if not bullet:
        return None
    rest = _CHECKBOX_RE.sub("", bullet.group("rest"), count=1)
    rest = _ASSERTION_RE.sub("", rest, count=1)
    num, _ = parse_marker(rest, fr_id=fr_id)
    return num


def insert_marker(line: str, ac_id: str) -> str:
    """``line`` with ``[ac_id]`` spliced in right after any checkbox/assertion
    decoration and before the criterion's own text."""
    bullet = BULLET_RE.match(line)
    lead, rest = bullet.group("lead"), bullet.group("rest")
    checkbox = _CHECKBOX_RE.match(rest)
    checkbox_text = checkbox.group(0) if checkbox else ""
    rest = rest[len(checkbox_text):]
    assertion = _ASSERTION_RE.match(rest)
    assertion_text = assertion.group(0) if assertion else ""
    rest = rest[len(assertion_text):]
    return f"{lead}{checkbox_text}{assertion_text}[{ac_id}] {rest}"


__all__ = [
    "embedded_ac_num",
    "insert_marker",
    "iter_all_bullet_positions",
    "iter_bullet_positions",
    "iter_heading_anchored_blocks",
]

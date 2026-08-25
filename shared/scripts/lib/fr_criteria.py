"""The ONE reader for an FR's acceptance criteria (campaign REQ3.04, sub-iterate R0).

Three parsers used to read "does this FR heading carry acceptance criteria,
and what are they" — ``lib/spec_parser.py`` (S5's FR-coherence check),
``tools/verifiers/_layer_coverage_ac.py`` (the cross-layer fold gate) and
``plugins/shipwright-compliance/scripts/audit/group_i_criteria.py`` (I6).
Only the third knew the shape ``/shipwright-project`` and ``/shipwright-adopt``
actually emit: ``### FR-XX.YY — Title`` headings (or ``**FR-XX.YY: Name**``
bold labels) followed directly by bare ``- (E) …`` / ``- [ ] …`` bullets, with
checkbox and assertion-marker decoration stripped, placeholder bullets
(``TBD``, ``N/A``, …) rejected, and a ``| FR-XX.YY | … |`` **table row
excluded on purpose** — every spec states each id in its requirements table,
so a row that counted as an anchor would make every requirement trivially
"have criteria".

This module is that shape, plus ``_layer_coverage_ac``'s continuation-line
rule (a criterion's guarantee often sits on the wrapped second line) and
whitespace normalisation (re-wrapping a paragraph is not a change). All three
callers delegate here; none keeps its own walk.

**Direction.** ``verifiers/`` and ``plugins/*/audit/`` read ``lib/`` — the
parser moved here, not the other way (precedent:
``tools/verifiers/_layer_coverage_evidence.py``).

**Two entry points, not one, because the callers ask two different
questions.** ``criteria_for`` / ``has_criteria`` answer "what does FR-X's
own section (wherever it is anchored, however many times) say" — the whole
block between an anchor and the next one is scanned, permissively, because a
legacy ``**Description:**`` / ``**Acceptance Criteria:**`` paragraph sitting
between the heading and the bullets must not hide them (group_i's original
behaviour; ``iter_anchored_blocks`` reproduces it exactly). ``leading_criteria``
answers a narrower, ADJACENCY-gated question for spec_parser's acceptance
fallback: does a bullet list start *immediately* under this heading, with no
prose paragraph first? Without that gate, the fallback would reach into
``.shipwright/planning/iterate/*.md`` — free-text documents that occasionally
grow a heading shaped like ``FR-XX.YY`` by coincidence — and read an unrelated
bullet list anywhere in the document as that FR's "acceptance". Today it is
"luck, not scope" that nothing there matches
(``test_requirements_catalog_parsers.py``); the gate makes it scope.

Pure: no I/O, greenfield-safe (empty input yields empty output).
"""

from __future__ import annotations

import re
from typing import Iterable, Iterator

#: An FR id in either separator style: ``FR-01.02``, ``FR 7``, ``FR-7``.
_FR_ID = r"FR[-\s]?\d+(?:\.\d+)*"

#: The id-specific START anchors. A heading anchor's rank is captured so the
#: matching terminator can be level-aware; a bold anchor has no rank of its
#: own, so ANY heading ends it (see ``iter_anchored_blocks``).
_HEADING_ANCHOR_RE = re.compile(rf"^(#{{1,6}})\s+(?P<id>{_FR_ID})\b")
_BOLD_ANCHOR_RE = re.compile(rf"^\s*\*\*\s*(?P<id>{_FR_ID})\b[^*]*\*\*\s*$")

#: Generic TERMINATOR sniffs — any heading, any FR-shaped bold label — used
#: only to find where the CURRENT block ends, never to name its id.
_ANY_HEADING = re.compile(r"^(#{1,6})\s+")
_ANY_BOLD_ANCHOR = re.compile(r"^\s*\*\*\s*FR[-\s]?\d")

#: A criterion bullet: ``-``/``*``/``+`` or ``1.``/``1)``, incl. the ``- [ ]``
#: checkbox form ``fr-authoring.md`` §3's worked example uses.
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<text>.*\S)\s*$")

#: Leading decoration stripped before a bullet's text is judged: a task
#: checkbox (``[ ]``/``[x]``) and the assertion marker (``(E)``) the house
#: style puts in front of "Given … when … then …".
_CHECKBOX = re.compile(r"^\[[ xX]\]\s*")
_ASSERTION_MARKER = re.compile(r"^\([A-Za-z]\)\s*")

#: Placeholder bodies meaning "not written yet", compared after stripping all
#: non-alphanumerics so ``TBD``, ``- [ ] TBA`` and ``N/A`` land on one token.
#: A bullet reduced to nothing (a bare ``- [ ]``) is likewise not a criterion.
_PLACEHOLDERS = frozenset({"tbd", "todo", "tba", "na", "none", "tbc"})


def normalise_fr_id(raw: str) -> str:
    """``FR 7`` -> ``FR-7``. Dotted ids keep their dots."""
    return raw.strip().replace(" ", "-")


def _flush(out: list[str], current: list[str]) -> None:
    joined = " ".join(" ".join(current).split())
    core = re.sub(r"[^0-9a-z]+", "", joined.lower())
    if core and core not in _PLACEHOLDERS:
        out.append(joined)


def criteria_texts(lines: Iterable[str]) -> list[str]:
    """The criteria in ``lines``, whitespace-normalised, continuation lines
    joined onto the bullet that opened them, placeholders dropped.

    A line indented under an open bullet extends it; a blank line or a line
    starting in column 0 ends it. Non-bullet lines before/between bullets are
    skipped, not treated as terminators — a body may carry prose (a
    ``**Description:**`` paragraph, an old ``**Acceptance Criteria:**``
    label) ahead of its bullets and still yield them.
    """
    out: list[str] = []
    current: list[str] | None = None
    for line in lines:
        bullet = _BULLET_RE.match(line)
        if bullet:
            if current is not None:
                _flush(out, current)
            text = _CHECKBOX.sub("", bullet.group("text")).strip()
            text = _ASSERTION_MARKER.sub("", text).strip()
            current = [text]
            continue
        if current is None:
            continue
        if not line.strip() or not line[:1].isspace():
            _flush(out, current)
            current = None
            continue
        current.append(line.strip())
    if current is not None:
        _flush(out, current)
    return out


def iter_anchored_blocks(content: str) -> Iterator[tuple[str, list[str]]]:
    """Yield ``(fr_id, block_lines)`` for every FR anchor (heading or bold
    form) in document order.

    A block runs from just after its anchor to the next heading of the SAME
    OR HIGHER rank (for a heading anchor) or ANY heading (for a bold anchor,
    which has no rank), or the next FR-shaped bold anchor — whichever comes
    first. A ``| FR-XX.YY | … |`` table row never opens a block: neither
    anchor regex matches a pipe-prefixed line.

    An id may legitimately be anchored more than once; each occurrence is
    yielded as its own block rather than merged, matching every caller's
    need to pool them (``criteria_for``) or keep them apart.
    """
    lines = content.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        heading = _HEADING_ANCHOR_RE.match(lines[i])
        bold = None if heading else _BOLD_ANCHOR_RE.match(lines[i])
        if not heading and not bold:
            i += 1
            continue
        fr_id = normalise_fr_id((heading or bold).group("id"))
        level = len(heading.group(1)) if heading else None
        j = i + 1
        while j < n:
            any_heading = _ANY_HEADING.match(lines[j])
            if any_heading and (level is None or len(any_heading.group(1)) <= level):
                break
            if _ANY_BOLD_ANCHOR.match(lines[j]):
                break
            j += 1
        yield fr_id, lines[i + 1:j]
        i = j


def criteria_for(content: str, fr_id: str) -> list[str]:
    """Every criterion text anchored to ``fr_id`` in ``content``, pooled
    across every occurrence of its anchor."""
    target = normalise_fr_id(fr_id)
    out: list[str] = []
    for anchored_id, block in iter_anchored_blocks(content):
        if anchored_id == target:
            out.extend(criteria_texts(block))
    return out


def has_criteria(content: str, fr_id: str) -> bool:
    """True when ``fr_id`` has at least one real acceptance criterion."""
    return bool(criteria_for(content, fr_id))


def leading_criteria(body_lines: list[str]) -> list[str]:
    """The bullet list that starts a heading's body, or ``[]``.

    Adjacency-gated: only the first non-blank line of ``body_lines`` is
    allowed to be prose-free. If it is not a bullet, this returns ``[]``
    outright — a bullet list further down, after a prose paragraph, does
    NOT count. See the module docstring for why this guard exists.

    Bounded to the CONTIGUOUS leading run (external code review, 2026-08-25):
    a bullet list ends at the first prose line, and nothing past that point
    is read — a later, unrelated list further down the SAME body (after that
    prose) must not extend it, even when the leading run itself was only a
    placeholder that `criteria_texts` filters to nothing.
    """
    i = 0
    n = len(body_lines)
    while i < n and not body_lines[i].strip():
        i += 1
    if i >= n or not _BULLET_RE.match(body_lines[i]):
        return []
    j = i
    while j < n:
        line = body_lines[j]
        if _BULLET_RE.match(line) or (line.strip() and line[:1].isspace()):
            j += 1
            continue
        if not line.strip():
            # A blank line may separate two bullets of the SAME list; only a
            # continuation into ANOTHER bullet keeps the run going.
            k = j
            while k < n and not body_lines[k].strip():
                k += 1
            if k < n and _BULLET_RE.match(body_lines[k]):
                j = k
                continue
        break
    return criteria_texts(body_lines[i:j])


__all__ = [
    "criteria_for",
    "criteria_texts",
    "has_criteria",
    "iter_anchored_blocks",
    "leading_criteria",
    "normalise_fr_id",
]

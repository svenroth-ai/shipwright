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

**One default semantics, one documented, tested opt-out — not two entry
points with silently different rules (2026-08-25, Stage-1 spec review).**
``criteria_for`` / ``has_criteria`` and ``leading_criteria`` now agree by
DEFAULT: both apply the same ADJACENCY gate — a bullet list only counts when
it starts at the block/body's first non-blank line, with no prose paragraph
first. This is what makes the convergence test
(``test_fr_criteria_convergence.py``) hold on the shipped shape (a heading
followed directly by bare bullets): every real spec this repo ships has no
prose between heading and bullets, so ``strict=True`` and the old permissive
scan agree on every one of them.

``criteria_for(..., strict=False)`` / ``has_criteria(..., strict=False)`` is
the one narrow, EXPLICIT, tested exception: a legacy ``**Description:**`` /
``**Acceptance Criteria:**`` label paragraph sitting between the heading and
the bullets must not hide them. Two real, pre-existing tests require exactly
this and would break if the default silently changed under them:
``plugins/shipwright-compliance/tests/test_group_i_criteria.py::test_legacy_bold_acceptance_label_still_counts``
(I6) and
``shared/tests/test_layer_coverage_criteria.py::test_prose_outside_a_criterion_is_not_a_criterion_change``
(the cross-layer gate). Both call sites pass ``strict=False`` explicitly,
each with a comment naming the test it preserves — see
``group_i_criteria.has_criteria`` and ``_layer_coverage_ac.criteria_digests``.

``leading_criteria`` stays adjacency-gated unconditionally (spec_parser's
S5 fallback never needs the permissive scan): without that gate the fallback
would reach into ``.shipwright/planning/iterate/*.md`` — free-text documents
that occasionally grow a heading shaped like ``FR-XX.YY`` by coincidence —
and read an unrelated bullet list anywhere in the document as that FR's
"acceptance". Today it is "luck, not scope" that nothing there matches
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

#: A single whole-line italic attribution, e.g. ``_Source: tests._`` —
#: `/shipwright-adopt`'s real per-FR shape (``spec_document.py:181-184``,
#: ``generate_adoption_artifacts.py:308``/``:376``). Tolerated as the ONE
#: exception to "first non-blank line must be a bullet" — narrower than
#: ``strict=False``'s whole-block scan, only one syntactically-marked line,
#: not arbitrary prose (Stage-3 doubt review, high, 2026-08-25: without
#: this, real adopt output read ZERO criteria under the shared default
#: while ``strict=False`` callers still saw them — AC-1's divergence,
#: reintroduced on real producer bytes).
_LEADING_ATTRIBUTION_RE = re.compile(r"^_[^_\n]+_\.?\s*$")


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

    A NESTED FR-shaped heading — deeper rank than its enclosing anchor, e.g.
    ``### FR-01.02`` inside a ``## FR-01.01`` block — still yields its OWN
    block (Stage-3 doubt review, medium, 2026-08-25): the outer scan
    advances one line at a time (``i += 1``, never jumping to the parent's
    end ``j``), so every line still gets its turn as a candidate anchor,
    including ones already spanned by an enclosing block. The old ``i = j``
    jump skipped that — a nested id was swallowed into its parent's span
    and never anchored at all, so it got no digest entry on EITHER side of
    a diff and ``criteria_changed_keys`` could never see it change.

    That fix does not separate the two spans: the parent's block still
    includes every line up to its own terminator, so a nested child's text
    is pooled into the PARENT's criteria too, not just its own — over-firing,
    this module's preferred failure direction, not a bug (Stage-3 doubt
    review, low, 2026-08-25).
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
        i += 1


def _leading_bullet_run(lines: list[str]) -> list[str]:
    """The slice of ``lines`` covering the CONTIGUOUS leading bullet run, or
    ``[]`` when the first non-blank line is not a bullet.

    Shared by ``leading_criteria`` and ``criteria_for(..., strict=True)`` so
    the two never drift apart again (2026-08-25, Stage-1 spec review): only
    the first non-blank line is allowed to be prose-free, and the run ends
    at the first prose line — a later, unrelated bullet list further down
    (after that prose) is never reached, even when the leading run itself
    was only a placeholder that ``criteria_texts`` filters to nothing
    (external code review, 2026-08-25). See the module docstring for why
    this adjacency gate exists.

    ONE exception, no wider (Stage-3 doubt review, high, 2026-08-25): a
    single whole-line italic attribution (``_LEADING_ATTRIBUTION_RE``,
    e.g. ``_Source: tests._``) between the heading and the bullets is
    skipped, not treated as the disqualifying prose line — this is
    `/shipwright-adopt`'s real, shipped shape, not a hypothetical. A
    SECOND non-bullet line still disqualifies the run; this does not
    reopen the door ``strict=True`` closed.
    """
    i = 0
    n = len(lines)
    while i < n and not lines[i].strip():
        i += 1
    if i < n and _LEADING_ATTRIBUTION_RE.match(lines[i].strip()):
        i += 1
        while i < n and not lines[i].strip():
            i += 1
    if i >= n or not _BULLET_RE.match(lines[i]):
        return []
    j = i
    while j < n:
        line = lines[j]
        if _BULLET_RE.match(line) or (line.strip() and line[:1].isspace()):
            j += 1
            continue
        if not line.strip():
            # A blank line may separate two bullets of the SAME list; only a
            # continuation into ANOTHER bullet keeps the run going.
            k = j
            while k < n and not lines[k].strip():
                k += 1
            if k < n and _BULLET_RE.match(lines[k]):
                j = k
                continue
        break
    return lines[i:j]


def block_criteria(lines: list[str], *, strict: bool = True) -> list[str]:
    """The criteria within an already-isolated anchor block or heading body.

    ``strict`` (default ``True``) applies the adjacency gate: only the
    CONTIGUOUS leading bullet run counts. ``strict=False`` is the narrow,
    documented exception — see the module docstring's "One default
    semantics" section for exactly which two call sites need it and why.
    """
    return criteria_texts(_leading_bullet_run(lines) if strict else lines)


def criteria_for(content: str, fr_id: str, *, strict: bool = True) -> list[str]:
    """Every criterion text anchored to ``fr_id`` in ``content``, pooled
    across every occurrence of its anchor. See ``block_criteria`` for
    ``strict``."""
    target = normalise_fr_id(fr_id)
    out: list[str] = []
    for anchored_id, block in iter_anchored_blocks(content):
        if anchored_id == target:
            out.extend(block_criteria(block, strict=strict))
    return out


def has_criteria(content: str, fr_id: str, *, strict: bool = True) -> bool:
    """True when ``fr_id`` has at least one real acceptance criterion. See
    ``block_criteria`` for ``strict``."""
    return bool(criteria_for(content, fr_id, strict=strict))


def leading_criteria(body_lines: list[str]) -> list[str]:
    """The bullet list that starts a heading's body, or ``[]``.

    spec_parser's S5 fallback — always ``strict`` (see ``block_criteria``);
    a thin, stably-named wrapper kept for that one caller's readability.
    """
    return block_criteria(body_lines, strict=True)


__all__ = [
    "block_criteria",
    "criteria_for",
    "criteria_texts",
    "has_criteria",
    "iter_anchored_blocks",
    "leading_criteria",
    "normalise_fr_id",
]

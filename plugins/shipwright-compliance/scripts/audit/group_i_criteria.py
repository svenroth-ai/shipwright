"""Does a requirement carry acceptance criteria at all? (Group I — I6)

Pure reader behind I6. Given a spec's text and an FR id, answer whether that
requirement has at least one real acceptance criterion.

**The rule this serves.** ``shared/fr-authoring.md`` §3a: a capability that
cannot be given acceptance criteria a single delivery would satisfy is too broad
and gets divided, and being unable to enumerate what would settle it is the
signal that it names several capabilities at once. Whether a requirement is
*too broad* is a judgement no parser can make. Whether it has **no criteria at
all** is observable, and that is the whole of what this module decides — hence
I6 is advisory, a warning that a human then judges.

**Why not reuse ``spec_parser``.** ``compute_fr_coherence`` (behind
``check_s5_fr_coherence``) recognises only FR bodies introduced by a
``**Acceptance Criteria:**`` bold label. The converged shape both
``/shipwright-project`` and ``/shipwright-adopt`` emit uses
``### FR-XX.YY — Title`` headings with bare bullets, so S5 reports every one of
this repo's own 18 requirements as missing acceptance while each is fully
elaborated. Reading the shape the producers actually write is the point.

**The two anchor forms, and one that is deliberately not an anchor.**

===========================================  ==============================
``### FR-XX.YY — Title`` + ``-``/``*``       adopt's ``artifact_writer``,
bullets                                      this repo's catalogue
``**FR-XX.YY: Name**`` + ``- [ ]`` boxes     ``spec-generation.md`` template
``| FR-XX.YY | … |``                         **NOT an anchor** — a table row
===========================================  ==============================

The table row exclusion is load-bearing rather than incidental: every spec
states each FR id in its requirements table, so if a row counted as an anchor
the pipe-delimited cells after it would read as content and every requirement
would trivially "have criteria" — the check would pass on precisely the specs it
exists to flag.

Pure: no I/O except the one file read in ``frs_without_criteria``.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Iterator

#: Any Markdown heading, with its level captured. A heading of the SAME or a
#: HIGHER rank ends the block; a deeper one (``#### Acceptance criteria`` under
#: an ``### FR-…``) stays inside it, because that is a subsection of the
#: requirement rather than the next requirement.
_ANY_HEADING = re.compile(r"^(#{1,6})\s+")

#: Any bold FR label, used only as a TERMINATOR — the anchor for the id being
#: asked about is built per-id below. Matches ``**FR-01.02: Name**`` and
#: ``**FR 7 — Name**``.
_ANY_BOLD_ANCHOR = re.compile(r"^\s*\*\*\s*FR[-\s]?\d")

#: A bullet: ``-``, ``*`` or ``+`` followed by whitespace.
_BULLET = re.compile(r"^[-*+]\s+(?P<body>.*)$")

#: Leading decoration stripped before asking whether a bullet says anything:
#: a task checkbox (``[ ]``/``[x]``) and the assertion marker (``(E)``) the
#: house style puts in front of "Given … when … then …".
_CHECKBOX = re.compile(r"^\[[ xX]\]\s*")
_ASSERTION_MARKER = re.compile(r"^\([A-Za-z]\)\s*")

#: Placeholder bodies that mean "not written yet". Compared after stripping all
#: non-alphanumerics, so ``TBD``, ``- [ ] TBA``, ``tbd.`` and ``N/A`` all land
#: on the same token. A bullet reduced to nothing at all (a bare ``- [ ]``) is
#: likewise not a criterion.
_PLACEHOLDERS = frozenset({"tbd", "todo", "tba", "na", "none", "tbc"})


def _is_criterion(line: str) -> bool:
    """True when this line is a bullet that actually states something."""
    m = _BULLET.match(line.strip())
    if not m:
        return False
    body = m.group("body").strip()
    body = _CHECKBOX.sub("", body).strip()
    body = _ASSERTION_MARKER.sub("", body).strip()
    core = re.sub(r"[^0-9a-z]+", "", body.lower())
    return bool(core) and core not in _PLACEHOLDERS


def _iter_blocks(content: str, fr_id: str) -> Iterator[list[str]]:
    """Yield the body lines of every block anchored on ``fr_id``.

    An id may legitimately be anchored more than once (a heading in the
    criteria section plus a bold label elsewhere); each block is yielded, and
    the caller stops at the first that carries a criterion.

    Both loops terminate at end-of-file naturally — a requirement that is the
    last thing in the document has no following anchor to stop at, and an
    earlier cut that required one silently dropped it.
    """
    esc = re.escape(fr_id)
    # The id must BEGIN the heading's content, not merely appear in it. A
    # heading that talks ABOUT a requirement — `### Notes for FR-01.01`,
    # `### Migration away from FR-01.01` — is not that requirement's criteria
    # block, and admitting it would let any stray bullet suppress the warning
    # for a requirement with no criteria at all: a false green in the check
    # built to catch precisely that.
    #
    # The catalogue's `<a id="fr-0101"></a>` anchors need no special case: they
    # sit on their own line, which simply matches nothing and is skipped.
    #
    # `\b` on the tail so `FR-01.02` is not satisfied by a block belonging to
    # `FR-01.029`; the anchored start rules out `XFR-01.02` symmetrically.
    heading_anchor = re.compile(rf"^(#{{1,6}})\s+{esc}\b")
    bold_anchor = re.compile(rf"^\s*\*\*\s*{esc}\b[^*]*\*\*\s*$")

    lines = content.splitlines()
    i = 0
    while i < len(lines):
        heading = heading_anchor.match(lines[i])
        bold = bold_anchor.match(lines[i]) if not heading else None
        if not heading and not bold:
            i += 1
            continue

        level = len(heading.group(1)) if heading else None
        j = i + 1
        while j < len(lines):
            h = _ANY_HEADING.match(lines[j])
            # A bold anchor has no rank of its own, so ANY heading ends it.
            if h and (level is None or len(h.group(1)) <= level):
                break
            if _ANY_BOLD_ANCHOR.match(lines[j]):
                break
            j += 1
        yield lines[i + 1:j]
        i = j


def has_criteria(content: str, fr_id: str) -> bool:
    """True when ``fr_id`` has at least one real acceptance criterion in ``content``."""
    return any(
        any(_is_criterion(line) for line in block)
        for block in _iter_blocks(content, fr_id)
    )


def frs_without_criteria(project_root: Path, rows: Iterable) -> list[str]:
    """Ids among ``rows`` whose OWN spec file gives them no acceptance criteria.

    Judged per spec file, not pooled across the catalogue. Pooling would let an
    elaborated ``FR-01.01`` in one split silently satisfy a bare ``FR-01.01`` in
    another — and while I4 forbids exactly that duplication, I6 must not depend
    on another check having already passed to avoid reporting a false green.

    A spec that cannot be read reports its rows as missing rather than raising:
    Group I is detective-only, and an unreadable spec is a finding, not a crash.
    """
    by_file: dict[str, list] = defaultdict(list)
    for row in rows:
        by_file[row.spec_path].append(row)

    missing: set[str] = set()
    for spec_path, group in by_file.items():
        try:
            content = (project_root / spec_path).read_text(
                encoding="utf-8", errors="ignore",
            )
        except OSError:
            content = ""
        missing.update(r.id for r in group if not has_criteria(content, r.id))
    return sorted(missing)


__all__ = ["frs_without_criteria", "has_criteria"]

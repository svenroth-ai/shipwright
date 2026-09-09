"""The parse/render half of ``write_context_term.py``, plus the sanctioned
public read API for ``CONTEXT.md``.

Split out of ``write_context_term.py`` the moment the combined file crossed
the 300-LOC bloat-baseline threshold (same precedent as
``_backfill_ac_provenance_apply.py``: the caller stays the upsert/CLI half,
this module is the document-format half). Renamed out of leading-underscore
``_context_md_format.py`` (doubt-reviewer D4, P4.1 Stage-3 review) once it
grew a second, cross-plugin caller: any future reader of sharpened terms
(e.g. P4.2's grill-trace completeness gate) must call :func:`read_terms`
here rather than importing a private module or re-deriving the parser —
forking the parser guarantees drift on exactly the edge cases (D2/D3) this
module exists to get right once.

Owns: ``shared/context-format.md``'s schema (Language / Relationships /
Flagged ambiguities). The write side (``parse_document`` /
``parse_language_entries`` / ``render_document`` / ...) is plain data-in,
data-out functions — no I/O, no CLI, no locking; ``read_terms`` is the one
function here that does I/O.

**Contract for matching (P4.2 and any other reader):** matching is
**exact-case, exact-prose** — no case-folding, no whitespace-insensitive
comparison. Two terms differing only in case (``"Order"`` vs ``"order"``)
are two different terms, never merged or deduplicated against each other.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Bootstrap: make lib.atomic_write importable regardless of caller (mirrors
# write_context_term.py's own _SCRIPTS_ROOT bootstrap, one level down).
_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from atomic_write import durable_read_bytes  # noqa: E402

# Canonical section order, per shared/context-format.md §2.
CANONICAL_SECTIONS = ("Language", "Relationships", "Flagged ambiguities")

DEFAULT_SUMMARY = "_(one-line project summary not yet recorded)_"

_TERM_RE = re.compile(r"^\*\*(.+?)\*\* — (.*)$")
_AVOID_RE = re.compile(r"^_Avoid_ (.*)$")
_H2_RE = re.compile(r"^## (.+?)\s*$")


@dataclass(frozen=True)
class Term:
    """One sharpened ``Language`` entry, as returned by :func:`read_terms`."""

    term: str
    definition: str
    avoid: str | None


def sanitize_field(value: str) -> str:
    """Collapse embedded newlines/whitespace to single spaces and strip —
    a stray newline would mis-parse as a new entry/heading next run."""
    return " ".join(value.split())


def detect_eol(content: str) -> str:
    """The file's own line-ending convention (never rewrite CRLF to LF)."""
    return "\r\n" if "\r\n" in content else "\n"


def term_markup_count(content: str, term: str) -> int:
    """Occurrences of the ``**term**`` bold-entry markup anywhere in
    ``content`` (header, any section, incl. unparsed raw blocks) — more than
    one means a hidden duplicate: a missing blank line before an existing
    entry swallowed it into a raw block, a heading-less file stashed it in
    the header, or a non-em-dash separator left it looking like a term but
    parsing as prose (doubt-reviewer D2, P4.1 Stage-3 review)."""
    return content.count(f"**{term}**")


def parse_document(
    lines: list[str], context_path: Path,
) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """``(header, sections, order)``: text before the first ``## `` heading,
    each heading's trimmed body, and heading names in file order (an
    unrecognized/hand-added section is preserved, not dropped)."""
    headers: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _H2_RE.match(line)
        if m:
            headers.append((i, m.group(1)))

    header_end = headers[0][0] if headers else len(lines)
    header = list(lines[:header_end])
    while header and not header[-1].strip():
        header.pop()

    sections: dict[str, list[str]] = {}
    order: list[str] = []
    for idx, (i, name) in enumerate(headers):
        if name in sections:
            raise ValueError(f"{context_path} has a duplicate '## {name}' heading "
                              "— fix by hand first (a 2nd occurrence would drop the 1st)")
        body_start = i + 1
        body_end = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        body = list(lines[body_start:body_end])
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        sections[name] = body
        order.append(name)

    return header, sections, order


def parse_language_entries(body: list[str]) -> list[dict]:
    """Ordered term entries (``{"term", "definition", "avoid"}``); unparseable
    hand-written prose is kept as ``{"term": None, "raw": [...]}`` and
    stitched back verbatim — never destroyed. A continuation line following a
    term line — one that is neither a new ``**Term**`` line nor an
    ``_Avoid_`` line — is absorbed (joined with a space) into the
    definition rather than left to become an orphaned raw block that
    injects a spurious blank line on re-render (doubt-reviewer D3, P4.1
    Stage-3 review; ``shared/context-format.md`` §2's own worked
    ``Cancellation`` example wraps this way)."""
    entries: list[dict] = []
    i = 0
    n = len(body)
    while i < n:
        line = body[i]
        if not line.strip():
            i += 1
            continue
        m = _TERM_RE.match(line)
        if not m:
            block = [line]
            i += 1
            while i < n and body[i].strip():
                block.append(body[i])
                i += 1
            entries.append({"term": None, "raw": block})
            continue
        term = m.group(1)
        definition_parts = [m.group(2)]
        i += 1
        while i < n and body[i].strip() and not _TERM_RE.match(body[i]) \
                and not _AVOID_RE.match(body[i]):
            definition_parts.append(body[i].strip())
            i += 1
        avoid = None
        if i < n:
            am = _AVOID_RE.match(body[i])
            if am:
                avoid = am.group(1)
                i += 1
        entries.append({
            "term": term,
            "definition": " ".join(definition_parts),
            "avoid": avoid,
        })
    return entries


def serialize_language_entries(entries: list[dict]) -> list[str]:
    out: list[str] = []
    for idx, e in enumerate(entries):
        if idx:
            out.append("")
        if e.get("term") is None:
            out.extend(e["raw"])
        else:
            out.append(f"**{e['term']}** — {e['definition']}")
            if e.get("avoid"):
                out.append(f"_Avoid_ {e['avoid']}")
    return out


def render_document(
    header: list[str], sections: dict[str, list[str]], order: list[str], eol: str = "\n",
) -> str:
    out = list(header)
    out.append("")
    for name in order:
        out.append(f"## {name}")
        body = sections.get(name, [])
        if body:
            out.append("")
            out.extend(body)
        out.append("")
    while out and not out[-1].strip():
        out.pop()
    return eol.join(out) + eol


def default_header(project_name: str, summary: str) -> list[str]:
    return [f"# CONTEXT.md — {project_name} domain glossary", "", summary]


def read_terms(context_path: Path) -> list[Term]:
    """The sanctioned way to read a target project's sharpened ``Language``
    terms back out of ``CONTEXT.md`` (doubt-reviewer D4, P4.1 Stage-3
    review) — e.g. P4.2's grill-trace completeness gate. Returns ``[]`` if
    the file doesn't exist or has no ``## Language`` section; a hand-written
    prose block with no parseable term contributes nothing to the result.
    **Failure contract:** raises ``ValueError`` on a duplicate ``## heading``
    (a malformed hand-edit, same as the write side) and ``UnicodeDecodeError``
    on non-UTF-8 content — neither is swallowed (P4.1 final review). Matching
    is exact-case, exact-prose — see the module Contract above. Reads through
    :func:`atomic_write.durable_read_bytes`, mirroring the write side's
    durability contract (a reader must not observe a mid-``os.replace``
    Windows delete-pending state as "file missing")."""
    if not context_path.exists():
        return []
    content = durable_read_bytes(context_path).decode("utf-8")
    lines = content.splitlines()
    _, sections, _ = parse_document(lines, context_path)
    entries = parse_language_entries(sections.get("Language", []))
    return [
        Term(term=e["term"], definition=e["definition"], avoid=e.get("avoid"))
        for e in entries
        if e.get("term") is not None
    ]

"""The parse/render half of ``write_context_term.py`` — split out the moment
the combined file crossed the 300-LOC bloat-baseline threshold (same
precedent as ``_backfill_ac_provenance_apply.py``: the caller stays the
upsert/CLI half, this module is the pure document-format half, and only the
caller imports it, never the other way round).

Owns: ``shared/context-format.md``'s schema (Language / Relationships /
Flagged ambiguities) as plain data-in, data-out functions — no I/O, no CLI,
no locking. Every function here is a pure transform over already-read text.
"""

from __future__ import annotations

import re
from pathlib import Path

# Canonical section order, per shared/context-format.md §2.
CANONICAL_SECTIONS = ("Language", "Relationships", "Flagged ambiguities")

DEFAULT_SUMMARY = "_(one-line project summary not yet recorded)_"

_TERM_RE = re.compile(r"^\*\*(.+?)\*\* — (.*)$")
_AVOID_RE = re.compile(r"^_Avoid_ (.*)$")
_H2_RE = re.compile(r"^## (.+?)\s*$")


def sanitize_field(value: str) -> str:
    """Collapse embedded newlines/whitespace to single spaces and strip —
    a stray newline would mis-parse as a new entry/heading next run."""
    return " ".join(value.split())


def detect_eol(content: str) -> str:
    """The file's own line-ending convention (never rewrite CRLF to LF)."""
    return "\r\n" if "\r\n" in content else "\n"


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
    stitched back verbatim — never destroyed."""
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
        term, definition = m.group(1), m.group(2)
        avoid = None
        i += 1
        if i < n:
            am = _AVOID_RE.match(body[i])
            if am:
                avoid = am.group(1)
                i += 1
        entries.append({"term": term, "definition": definition, "avoid": avoid})
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

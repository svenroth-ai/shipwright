"""Write/update a sharpened domain term into a target project's ``CONTEXT.md``.

``shared/requirement-elicitation.md`` §4 fires the moment a term is captured,
challenged, or replaced with a precise one during a grilling interview; §7
requires the result land in ``CONTEXT.md`` **the moment it is resolved** —
not batched after the interview ends. This is that producer: the ONE code
path that writes ``CONTEXT.md``, following ``shared/context-format.md``'s
schema exactly (Language / Relationships / Flagged ambiguities — this tool
only writes ``Language`` entries, the ones a sharpened term produces).

Usage:

    uv run shared/scripts/tools/write_context_term.py \\
        --project-root . --term "Order" \\
        --definition "a customer's confirmed purchase of one or more items." \\
        --avoid '"cart" for a confirmed order — a cart is unconfirmed.'

**Idempotent + contract (external plan+code review, P4.1):** an unchanged
term set re-runs byte-identical, incl. CRLF/LF convention. Re-sharpening a
term overwrites in place (never a second entry); every other entry and
section round-trips untouched. All free-text fields (``--term``,
``--definition``, ``--avoid``, ``--project-name``, ``--summary``) are
sanitized to single-line prose (a stray newline would otherwise mis-parse
as a new entry/heading); a blank term/definition is rejected, ``--term``
may not contain ``**`` (the entry delimiter), a duplicate ``## heading`` in
an existing file is rejected rather than silently dropping the first
occurrence, and ``--project-root``/``--context-path``'s parent must already
exist (never silently created).

Exit codes: 0 on success (created/appended/updated/unchanged); 1 on a lock
timeout, I/O error, or any rejected input above.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Bootstrap: make lib.file_lock importable when this file is run directly.
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.file_lock import LockTimeout, file_lock  # noqa: E402

# Canonical section order, per shared/context-format.md §2.
CANONICAL_SECTIONS = ("Language", "Relationships", "Flagged ambiguities")

DEFAULT_SUMMARY = "_(one-line project summary not yet recorded)_"

_TERM_RE = re.compile(r"^\*\*(.+?)\*\* — (.*)$")
_AVOID_RE = re.compile(r"^_Avoid_ (.*)$")
_H2_RE = re.compile(r"^## (.+?)\s*$")


def _sanitize_field(value: str) -> str:
    """Collapse embedded newlines/whitespace to single spaces and strip —
    a stray newline would mis-parse as a new entry/heading next run."""
    return " ".join(value.split())


def _detect_eol(content: str) -> str:
    """The file's own line-ending convention (never rewrite CRLF to LF)."""
    return "\r\n" if "\r\n" in content else "\n"


def find_context_file(project_root: Path) -> Path:
    """``CONTEXT.md`` for ``project_root`` (single-domain layout only)."""
    return project_root / "CONTEXT.md"


def _parse_document(lines: list[str]) -> tuple[list[str], dict[str, list[str]], list[str]]:
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
            raise ValueError(f"CONTEXT.md has a duplicate '## {name}' heading "
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


def _parse_language_entries(body: list[str]) -> list[dict]:
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


def _serialize_language_entries(entries: list[dict]) -> list[str]:
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


def _render_document(
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


def _default_header(project_name: str, summary: str) -> list[str]:
    return [f"# CONTEXT.md — {project_name} domain glossary", "", summary]


def upsert_term(
    context_path: Path,
    *,
    term: str,
    definition: str,
    avoid: str | None = None,
    project_name: str = "",
    summary: str = "",
) -> dict[str, object]:
    """Create/update ``context_path`` with one sharpened ``Language`` term
    (caller holds the lock — see ``main()``)."""
    term = _sanitize_field(term)
    definition = _sanitize_field(definition)
    avoid = _sanitize_field(avoid) if avoid else None
    if not term:
        raise ValueError("--term must not be blank")
    if not definition:
        raise ValueError("--definition must not be blank")
    if "**" in term:
        raise ValueError("--term must not contain '**' — it is the entry delimiter")

    existed = context_path.exists()
    eol = "\n"
    if existed:
        # newline="" preserves the file's own CRLF/LF; read_text() only grew
        # that kwarg in 3.13, so .open() is used (CI is pinned to 3.11).
        with context_path.open("r", encoding="utf-8", newline="") as fh:
            content = fh.read()
        eol = _detect_eol(content)
        lines = content.splitlines()  # newline-aware regardless of "newline="
        header, sections, order = _parse_document(lines)
    else:
        # Sanitized like the term fields: an unsanitized --project-name/--summary
        # could inject a heading/entry line into the header and corrupt the schema.
        name = _sanitize_field(project_name) or context_path.parent.name or "project"
        clean_summary = _sanitize_field(summary) or DEFAULT_SUMMARY
        header = _default_header(name, clean_summary)
        sections = {}
        order = []

    for name in CANONICAL_SECTIONS:
        if name not in order:
            order.append(name)
        sections.setdefault(name, [])

    entries = _parse_language_entries(sections["Language"])

    status = "created" if not existed else None
    found = False
    for e in entries:
        if e.get("term") == term:
            changed = e.get("definition") != definition or e.get("avoid") != avoid
            e["definition"] = definition
            e["avoid"] = avoid
            found = True
            status = status or ("updated" if changed else "unchanged")
            break
    if not found:
        entries.append({"term": term, "definition": definition, "avoid": avoid})
        status = status or "appended"

    sections["Language"] = _serialize_language_entries(entries)

    new_content = _render_document(header, sections, order, eol=eol)

    old_content = content if existed else None
    if new_content != old_content:
        durable_atomic_write(context_path, new_content)
        write_status = status if status != "unchanged" else "rewritten"
    else:
        write_status = "unchanged"

    return {
        "status": write_status,
        "context_path": str(context_path),
        "term": term,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--term", required=True)
    parser.add_argument("--definition", required=True)
    parser.add_argument("--avoid", default=None)
    parser.add_argument("--project-name", default="", help="Only used if CONTEXT.md is new")
    parser.add_argument("--summary", default="", help="One-liner; only used if CONTEXT.md is new")
    parser.add_argument("--context-path", default="", help="Explicit path override")
    parser.add_argument("--lock-timeout", type=float, default=5.0)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if args.context_path:
        context_path = Path(args.context_path).resolve()
        if not context_path.parent.is_dir():
            print(f"ERROR: --context-path parent does not exist: {context_path.parent}",
                  file=sys.stderr)
            return 1
    else:
        if not project_root.is_dir():
            print(f"ERROR: --project-root does not exist: {project_root}", file=sys.stderr)
            return 1
        context_path = find_context_file(project_root)
    lock_path = context_path.with_suffix(context_path.suffix + ".lock")

    try:
        with file_lock(lock_path, timeout_seconds=args.lock_timeout):
            result = upsert_term(
                context_path,
                term=args.term,
                definition=args.definition,
                avoid=args.avoid,
                project_name=args.project_name,
                summary=args.summary,
            )
    except (LockTimeout, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

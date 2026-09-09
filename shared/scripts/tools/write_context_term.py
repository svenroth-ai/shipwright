"""Write/update a sharpened domain term into a target project's ``CONTEXT.md``.

``shared/requirement-elicitation.md`` §4 fires the moment a term is captured,
challenged, or replaced with a precise one during a grilling interview; §7
requires the result land in ``CONTEXT.md`` **the moment it is resolved** —
not batched after the interview ends. This is that producer: the ONE code
path that writes ``CONTEXT.md``, following ``shared/context-format.md``'s
schema exactly (Language / Relationships / Flagged ambiguities — this tool
only writes ``Language`` entries, the ones a sharpened term produces). The
document-format parse/render internals live in the sibling
``_context_md_format.py``.

Usage:

    uv run shared/scripts/tools/write_context_term.py \\
        --project-root . --term "Order" \\
        --definition "a customer's confirmed purchase of one or more items." \\
        --avoid '"cart" for a confirmed order — a cart is unconfirmed.'

**Idempotent + contract (external plan+code review, P4.1):** an unchanged
term set re-runs byte-identical, incl. CRLF/LF convention. Re-sharpening a
term overwrites in place (never a second entry); every other entry/section
round-trips untouched. **Omitting ``--avoid`` on a re-sharpen KEEPS the
existing ``_Avoid_`` line** (not "clear it"); ``--clear-avoid`` deletes it
explicitly (mutually exclusive with ``--avoid``). Free-text fields are
sanitized to single-line prose (a stray newline would otherwise mis-parse
as a new entry/heading); a blank term/definition is rejected, ``--term``
may not contain ``**`` (the entry delimiter), a duplicate ``## heading`` in
an existing file is rejected rather than silently dropping the first
occurrence, and ``--project-root``/``--context-path``'s parent must
already exist (never silently created).

Exit codes: 0 on success (created/appended/updated/unchanged); 1 on a lock
timeout, I/O error, or any rejected input above.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Bootstrap: make lib.file_lock importable when this file is run directly.
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.file_lock import LockTimeout, file_lock  # noqa: E402

from tools._context_md_format import (  # noqa: E402
    CANONICAL_SECTIONS,
    DEFAULT_SUMMARY,
    default_header,
    detect_eol,
    parse_document,
    parse_language_entries,
    render_document,
    sanitize_field,
    serialize_language_entries,
)


def upsert_term(
    context_path: Path,
    *,
    term: str,
    definition: str,
    avoid: str | None = None,
    clear_avoid: bool = False,
    project_name: str = "",
    summary: str = "",
) -> dict[str, object]:
    """Create/update ``context_path`` with one sharpened ``Language`` term
    (caller holds the lock — see ``main()``). ``avoid=None`` keeps the
    existing ``_Avoid_`` line; ``clear_avoid=True`` deletes it."""
    term = sanitize_field(term)
    definition = sanitize_field(definition)
    avoid = sanitize_field(avoid) if avoid else None
    if not term:
        raise ValueError("--term must not be blank")
    if not definition:
        raise ValueError("--definition must not be blank")
    if "**" in term:
        raise ValueError("--term must not contain '**' — it is the entry delimiter")
    if clear_avoid and avoid:
        raise ValueError("--avoid and --clear-avoid are mutually exclusive")

    existed = context_path.exists()
    eol = "\n"
    if existed:
        # newline="" preserves CRLF/LF; read_text() only grew that kwarg in
        # 3.13, so .open() is used (CI is pinned to 3.11).
        with context_path.open("r", encoding="utf-8", newline="") as fh:
            content = fh.read()
        eol = detect_eol(content)
        lines = content.splitlines()  # newline-aware regardless of "newline="
        header, sections, order = parse_document(lines, context_path)
    else:
        # Sanitized like the term fields — an unsanitized value could inject
        # a heading/entry line into the header.
        name = sanitize_field(project_name) or context_path.parent.name or "project"
        clean_summary = sanitize_field(summary) or DEFAULT_SUMMARY
        header = default_header(name, clean_summary)
        sections = {}
        order = []

    for name in CANONICAL_SECTIONS:
        if name not in order:
            order.append(name)
        sections.setdefault(name, [])

    entries = parse_language_entries(sections["Language"])

    status = "created" if not existed else None
    found = False
    for e in entries:
        if e.get("term") == term:
            # avoid=None keeps the existing line; only an EXPLICIT --avoid
            # or --clear-avoid changes it.
            if clear_avoid:
                new_avoid = None
            elif avoid is not None:
                new_avoid = avoid
            else:
                new_avoid = e.get("avoid")
            changed = e.get("definition") != definition or e.get("avoid") != new_avoid
            e["definition"] = definition
            e["avoid"] = new_avoid
            found = True
            status = status or ("updated" if changed else "unchanged")
            break
    if not found:
        entries.append({"term": term, "definition": definition, "avoid": avoid})
        status = status or "appended"

    sections["Language"] = serialize_language_entries(entries)

    new_content = render_document(header, sections, order, eol=eol)

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
    # Windows console stderr defaults to strict-mode cp1252; without this a
    # non-ASCII error (e.g. a duplicate-heading path) raises UnicodeEncodeError
    # instead of a clean exit 1.
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--term", required=True)
    parser.add_argument("--definition", required=True)
    parser.add_argument("--avoid", default=None)
    parser.add_argument("--clear-avoid", action="store_true",
                         help="delete an existing --avoid line (omitting --avoid keeps it)")
    parser.add_argument("--project-name", default="", help="only used if CONTEXT.md is new")
    parser.add_argument("--summary", default="", help="only used if CONTEXT.md is new")
    parser.add_argument("--context-path", default="", help="explicit path override")
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
        context_path = project_root / "CONTEXT.md"  # single-domain layout only
    lock_path = context_path.with_suffix(context_path.suffix + ".lock")

    try:
        with file_lock(lock_path, timeout_seconds=args.lock_timeout):
            result = upsert_term(
                context_path,
                term=args.term,
                definition=args.definition,
                avoid=args.avoid,
                clear_avoid=args.clear_avoid,
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

"""Write/update a sharpened domain term into a target project's ``CONTEXT.md``.

``shared/requirement-elicitation.md`` §4 fires the moment a term is captured,
challenged, or replaced with a precise one during a grilling interview; §7
requires the result land in ``CONTEXT.md`` **the moment it is resolved** —
not batched after the interview ends. This is that producer: the ONE code
path that writes ``CONTEXT.md``, following ``shared/context-format.md``'s
schema exactly (Language / Relationships / Flagged ambiguities — this tool
only writes ``Language`` entries, the ones a sharpened term produces).
**No other write path is safe while an interview is running** — a hand-edit
(Edit/Write, uncoordinated with this tool's ``file_lock``) racing this
producer's atomic full-file replace can silently drop a term; see
``interview-protocol.md`` for the "no hand-edits during elicitation" rule
this requires. Reading the file back is a separate, sanctioned API — see
``context_md_format.read_terms()``, the sibling module the document-format
parse/render internals (and this contract's "exact-case, exact-prose
matching, no folding" guarantee) live in.

Usage — **``--payload-file`` is the sanctioned way to pass free text from an
interview** (P4.1 final review): the caller writes a small JSON file (via the
Write tool, never a shell command — so no shell quoting of user-dictated text
ever occurs) and every value that reaches this script's argv is then a fixed,
known string:

    uv run shared/scripts/tools/write_context_term.py \\
        --project-root . --payload-file /path/to/payload.json

where ``payload.json`` is ``{"term": "...", "definition": "...",
"avoid": "..." | null, "clear_avoid": false, "project_name": "...",
"summary": "..."}`` (only ``term``/``definition`` are required). This is not
a stylistic preference: substituting free interview text directly into a
shell-quoted ``--term '<value>'`` breaks out of the quoting the instant the
value itself contains a single quote (plausible, ordinary English — "the
customer's cart") and the rest of the string is then interpreted as shell
syntax. JSON has its own, much simpler escaping (backslash-escape ``"`` and
``\\``) that an LLM composing the payload text handles natively — there is
no quote-breakout surface because no shell ever parses the free text at all.

``--term``/``--definition``/``--avoid`` (below) remain for callers that
already hold trusted, non-shell-composed values (tests, other scripts) —
never for a value assembled from unsanitized interview text:

    uv run shared/scripts/tools/write_context_term.py \\
        --project-root . --term "Order" \\
        --definition "a customer's confirmed purchase of one or more items." \\
        --avoid '"cart" for a confirmed order — a cart is unconfirmed.'

**Idempotent + contract (external plan+code review, P4.1):** an unchanged
term set re-runs byte-identical, incl. CRLF/LF convention. Re-sharpening a
term overwrites in place (never a second entry); every other entry/section
is preserved, except a hand-written definition that wraps onto a
continuation line (``shared/context-format.md`` §2's own ``Cancellation``
example) — that is **normalized onto a single line** (absorbed into the
definition, joined with a space) rather than left to become an orphaned
raw block. **Omitting ``--avoid`` on a re-sharpen KEEPS the existing
``_Avoid_`` line** (not "clear it"); ``--clear-avoid`` deletes it
explicitly (mutually exclusive with ``--avoid``). Free-text fields are
sanitized to single-line prose (a stray newline would otherwise mis-parse
as a new entry/heading); a blank/whitespace-only term, definition, or (if
given at all) ``--avoid`` is rejected, ``--term`` may not contain ``**``
(the entry delimiter), a duplicate ``## heading`` in an existing file is
rejected rather than silently dropping the first occurrence, a hidden
duplicate of the term being written **in the header or the Language
section** (an existing occurrence a missing blank line, a heading-less
file, or a non-em-dash separator kept out of reach of matching — never a
legitimate bold cross-reference to the same term inside ``Relationships``/
``Flagged ambiguities``, which this check does not scan) is rejected rather
than silently written a second time, and ``--project-root``/
``--context-path``'s parent must already exist (never silently created).

**Known limitation:** this tool only ever writes ``Language`` entries.
``Relationships`` and ``Flagged ambiguities`` (also required by
requirement-elicitation.md §4/§7) currently have no producer and must still
be hand-edited — a gap the "no hand-edits while an interview is running"
rule above does not close, only fences off from racing this tool's writes.

Exit codes: 0 on success — ``status`` is one of ``created`` (new file),
``appended`` (new term, existing file), ``updated`` (an existing term's
definition/avoid changed), ``unchanged`` (re-run with identical content,
no write performed), or ``rewritten`` (an existing term matched with no
value change, but the file was re-serialized anyway — e.g. a hand-written
entry's whitespace was normalized — so a write DID happen; distinct from
``unchanged`` so a caller can tell whether the file's mtime moved). Exit 1
on a lock timeout, I/O error, or any rejected input above.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Bootstrap: make lib.file_lock importable when this file is run directly.
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write, durable_read_bytes  # noqa: E402
from lib.file_lock import LockTimeout, file_lock  # noqa: E402

from tools._write_context_term_cli import PayloadError, build_arg_parser, resolve_fields  # noqa: E402
from tools.context_md_format import (  # noqa: E402
    CANONICAL_SECTIONS,
    DEFAULT_SUMMARY,
    default_header,
    detect_eol,
    parse_document,
    parse_language_entries,
    render_document,
    sanitize_field,
    serialize_language_entries,
    split_lines_strict,
    term_markup_count,
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
    if avoid is not None:
        # A given-but-blank --avoid (e.g. "   ") must be rejected outright,
        # not silently fall through as if it were the same as "omitted" —
        # sanitizing it to "" first would otherwise take the same path as
        # --clear-avoid while --avoid + --clear-avoid together stayed
        # accepted, contradicting the documented mutual exclusion
        # (doubt-reviewer D5, P4.1 Stage-3 review).
        avoid = sanitize_field(avoid)
        if not avoid:
            raise ValueError(
                "'avoid' must not be blank — omit it (or pass null in "
                "--payload-file) to keep an existing _Avoid_ line, or set "
                "clear_avoid/--clear-avoid to delete one"
            )
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
    content = None
    if existed:
        # newline="" (via manual decode, not a text-mode open()) preserves
        # CRLF/LF; universal-newline translation is a TextIOWrapper feature,
        # so a plain bytes.decode() never performs it either. Reads through
        # durable_read_bytes, mirroring the write side's durability contract
        # (doubt-reviewer D6, P4.1 Stage-3 review) — a bare .open() does not
        # retry a Windows delete-pending PermissionError from a concurrent
        # durable_atomic_write holder.
        content = durable_read_bytes(context_path).decode("utf-8")
        eol = detect_eol(content)
        # Line-anchored, CRLF/CR/LF only — never the wider Unicode
        # line-separator set str.splitlines() also treats as a break (see
        # split_lines_strict's docstring).
        lines = split_lines_strict(content)
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

    # A hidden pre-existing occurrence of this exact term's markup (missing
    # blank line before it, a heading-less file that stashed it in the
    # header, or a non-em-dash separator) would otherwise let a second,
    # invisible entry through silently — refuse loudly instead, the same way
    # the duplicate-heading check above does (doubt-reviewer D2, P4.1
    # Stage-3 review). Scanned over header + Language ONLY — all three
    # hidden-duplicate shapes live there; a term legitimately reappears bold
    # as a cross-reference in Relationships/Flagged ambiguities (context-
    # format.md §2's own worked example: "the paying **Customer**; ... a
    # **User**."), and scanning the whole document flagged that as a false
    # duplicate (doubt-reviewer follow-up, P4.1 final review).
    language_scan_text = "\n".join(header + sections["Language"])
    if term_markup_count(language_scan_text, term) > 1:
        raise ValueError(
            f"{context_path} already contains an unparsed '**{term}**' "
            "occurrence elsewhere in the header or Language section (a "
            "missing blank line before it, no '## ' heading before the "
            "Language section, or a non-em-dash separator after the term) "
            "— fix by hand first; refusing to write a second, hidden "
            "duplicate"
        )

    if new_content != content:
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
    # Windows console streams default to strict-mode cp1252; without this a
    # non-ASCII error or --help text (em dash) mis-encodes for a UTF-8 reader.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = build_arg_parser(__doc__.split("\n")[0])
    args = parser.parse_args()

    try:
        fields = resolve_fields(args)
    except PayloadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

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
                term=fields["term"],
                definition=fields["definition"],
                avoid=fields["avoid"],
                clear_avoid=fields["clear_avoid"],
                project_name=fields["project_name"],
                summary=fields["summary"],
            )
    except (LockTimeout, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

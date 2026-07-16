"""Idempotent tag-writing for the backfill engine (traceability TT6).

Inserts an ``@FR`` tag into a test file in the idiom the frozen ``fr_tag_grammar``
reads back: a ``@pytest.mark.covers("FR-XX.YY")`` decorator for pytest, a
``// @covers FR-XX.YY`` comment for TS/JS. Split out of ``backfill_test_links.py``
to keep both under the 300-LOC cap (ADR-099).

Safety + idempotency:

* Writes are line-number insertions above the parsed test declaration (never a
  regex rewrite of the test body), applied bottom-up per file so an earlier edit
  never shifts a later line index.
* The file's LF/CRLF style is preserved CROSS-PLATFORM: the file is read as raw
  bytes and rewritten with :func:`Path.write_bytes` using the detected ending —
  NOT ``read_text``/``write_text``, whose universal-newline + ``os.linesep``
  translation would silently rewrite CRLF→LF on a Linux runner (a green-local /
  red-CI trap) and only accidentally preserve CRLF on Windows.
* Best-effort per file: a non-UTF-8 source (cp1252/latin-1 — real Windows
  history in this repo) is SKIPPED (never a lossy rewrite) and recorded as a
  failure, so one undecodable file can never abort the batch mid-loop or lose
  the report of what was done.
* A deterministic pytest match is ALWAYS tagged (AC1): if the file does not
  already bind ``pytest`` (checked via the AST, not a fragile substring — a
  ``# import pytest`` comment must not satisfy it, else the emitted decorator
  raises ``NameError``), ``import pytest`` is inserted after the docstring /
  ``__future__`` imports.
* The engine only calls this for tests it found UNTAGGED, so a re-run (which
  re-scans and sees the written tag) writes nothing new.
"""

from __future__ import annotations

import ast
from pathlib import Path


def make_tag_line(rel_path: str, indent: int, fr: str) -> str:
    pad = " " * indent
    if rel_path.endswith(".py"):
        return f'{pad}@pytest.mark.covers("{fr}")'
    return f"{pad}// @covers {fr}"


def pytest_bound(source: str) -> bool:
    """True iff the name ``pytest`` is really imported (AST, not a substring).

    ``from pytest import mark`` does not bind ``pytest``; a comment/docstring
    mention must not either — else the inserted decorator raises ``NameError``.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "import pytest" in source     # unparsable: best-effort, conservative
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (alias.asname or alias.name.split(".")[0]) == "pytest":
                    return True
    return False


def pytest_import_line(source: str) -> int:
    """0-based line index at which to insert ``import pytest`` — after the module
    docstring and any ``from __future__`` imports, else the top of the file."""
    try:
        body = ast.parse(source).body
    except SyntaxError:
        return 0
    insert, idx = 0, 0
    if body and isinstance(body[0], ast.Expr) and isinstance(
            getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
        insert, idx = body[0].end_lineno or 0, 1
    while idx < len(body) and isinstance(body[idx], ast.ImportFrom) and body[idx].module == "__future__":
        insert = body[idx].end_lineno or insert
        idx += 1
    return insert


def apply_writes(project_root: Path, writes: list[tuple]) -> tuple[list, list]:
    """Insert every ``(record, candidate)`` tag into its file.

    Returns ``(applied, failures)`` — ``applied`` is one entry per written tag;
    ``failures`` is one ``{"test", "fr", "reason"}`` dict per (record, candidate)
    that could not be written (e.g. a non-UTF-8 source), so the caller can always
    account for every intended write even if a file is skipped.
    """
    applied: list[tuple] = []
    failures: list[dict] = []
    by_file: dict[str, list[tuple]] = {}
    for record, cand in writes:
        by_file.setdefault(record.rel_path, []).append((record, cand))
    for rel, items in by_file.items():
        abs_path = Path(project_root) / rel
        try:
            # Read RAW bytes (not read_text): universal-newline mode would strip
            # \r\n so the CRLF detection below would be dead on every platform.
            text = abs_path.read_bytes().decode("utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            reason = "non_utf8_source" if isinstance(exc, UnicodeDecodeError) else "read_error"
            failures.extend({"test": r.test_id, "fr": c.fr, "reason": reason} for r, c in items)
            continue
        newline = "\r\n" if "\r\n" in text else "\n"     # detected from the RAW content
        needs_import = rel.endswith(".py") and not pytest_bound(text)
        import_at = pytest_import_line(text) if needs_import else -1
        lines = text.splitlines()
        for record, cand in sorted(items, key=lambda ic: -ic[0].decl_line):
            lines.insert(record.decl_line, make_tag_line(rel, record.indent, cand.fr))
            applied.append((record, cand))
        if needs_import:  # header region is above every test decl, so this index is still valid
            lines.insert(import_at, "import pytest")
        # write_bytes with the DETECTED newline: no os.linesep translation, so the
        # source ending is preserved identically on Windows AND Linux CI.
        abs_path.write_bytes((newline.join(lines) + newline).encode("utf-8"))
    return applied, failures


__all__ = ["make_tag_line", "pytest_bound", "pytest_import_line", "apply_writes"]

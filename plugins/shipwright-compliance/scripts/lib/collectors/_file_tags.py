"""Per-file tag extraction for the ``test_links`` collector: one call per test file.

The frozen ``fr_tag_grammar`` reference parser binds a tag to a single test declaration
on a single line. Three real-world shapes fall outside that, and all three are handled
here so ``test_links.build_manifest`` keeps exactly one call site:

* **multi-line TS/JS declarations** — Prettier wraps a long ``test(`` call so the title
  and the ``{ tag: [...] }`` option land on the lines AFTER ``test(``. The reference
  parser (and the untagged enumeration, which shares its matcher) then sees no test at
  all. :func:`join_multiline_decls` folds such a declaration head back onto one line
  before anything parses it, so the tag, the title and the enumeration agree;
* **suite-level tags** (``describe``) — :mod:`._suite_tags`, unchanged;
* **class-level and module-level pytest marks** — ``@pytest.mark.covers`` on a ``class``
  applies to every ``test*`` method in it (pytest's own marker semantics), and a
  module-level ``pytestmark = pytest.mark.covers(...)`` (or a list of marks) to every
  ``test*`` function in the file. :func:`python_scope_marks` binds them, reusing the
  grammar's own marker test and FR/AC canonicaliser so the valid/malformed split cannot
  drift from the frozen grammar.

A propagated hit that duplicates a per-test hit (same test, FR and AC) is dropped, so a
method carrying the same tag as its class is not linked twice.
"""

from __future__ import annotations

import ast
import re

from ._lib_loader import load_shared_lib
from ._suite_tags import propagate_suite_tags

# The gate's own lexer (regex literals, JSX text, comments), so a wrapped ``.each`` table closes at
# the same paren for the collector and the test-tag gate.
_lex = load_shared_lib("ts_lexer").lex
_JSX_SUFFIXES = (".tsx", ".jsx", ".js")  # same set as the gate; never ``.ts``, where ``<T>x`` is a cast

# A declaration head left open at the end of its line, as a statement of its own:
# ``test(`` / ``it.only(`` / ``test.describe(`` / ``describe(`` with nothing after the paren.
_OPEN_DECL_RE = re.compile(r"^\s*(?:await\s+)?(?:it|test|describe)(?:\.\w+)*\s*\(\s*$")
# The line that starts the callback — where the declaration head ends — judged with string
# literals blanked, so a title such as 'the login function works' does not end the head.
_CALLBACK_RE = re.compile(r"=>|\bfunction\b")
_STRING_RE = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")
_MAX_HEAD_LINES = 8
# A data-driven head whose table wraps: ``it.each([`` / ``test.each(`` / ``test.each`` + backtick.
_EACH_OPEN_RE = re.compile(r"^\s*(?:await\s+)?(?:it|test)(?:\.(?!(?:describe|step)\b)\w+)*\.each\s*(?=[(`])")
_EACH_BARE_RE = re.compile(r"^\s*(?:await\s+)?(?:it|test)(?:\.(?!(?:describe|step)\b)\w+)*\.each\s*$")
_TITLE_OPEN_RE =re.compile(r"[ \t]*\(\s*['\"`]")
_MAX_TABLE_LINES = 400


def join_multiline_decls(source: str, jsx: bool = True) -> str:
    """Fold a wrapped ``test(``/``it(``/``describe(`` head onto one line.

    Joins the open line with the following lines up to and including the first line that
    starts the callback (``=>`` / ``function``). Gives up — leaving the source untouched
    for that declaration — when no callback line appears within ``_MAX_HEAD_LINES`` or a
    comment line interrupts the head, so an unusual shape degrades to the reference
    parser's behaviour instead of being mangled. Braces are preserved, only moved onto one
    line, so the suite-scope brace depth is unchanged. ``jsx`` says whether JSX text is lexed
    (the gate's rule: not for a ``.ts`` file).
    """
    lines = source.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        end = _each_end(lines, i, jsx)
        if end is None and _OPEN_DECL_RE.search(lines[i]):
            end = _head_end(lines, i)
        if end is None:
            out.append(lines[i])
            i += 1
            continue
        out.append(" ".join([lines[i].rstrip()] + [ln.strip() for ln in lines[i + 1:end + 1]]))
        i = end + 1
    return "\n".join(out) + ("\n" if source.endswith("\n") else "")


def _each_end(lines: list[str], start: int, jsx: bool = True) -> int | None:
    """Index of the line where the ``.each`` table opened at ``start`` closes and the title
    quote follows (``])('title'``); ``None`` when the head is one line or not a data-driven head."""
    first = lines[start]
    if not (_EACH_OPEN_RE.match(first) or _EACH_BARE_RE.match(first)):  # `.each` alone: the table opens below
        return None
    text = "\n".join(lines[start:start + _MAX_TABLE_LINES])
    m = _EACH_OPEN_RE.match(text)
    if not m:
        return None
    i, n = m.end(), len(text)
    if text[i] == "`":
        i = _quoted_end(text, i)
        if i is None:
            return None
    else:
        # `i` is at the table's `(`; the lexer skips strings, comments, regex literals and JSX text and
        # stops at the `)` that closes it.
        _, close = _lex(text, i + 1, jsx, stop=True)
        if close >= n or text[close] != ")":
            return None
        i = close + 1
    title = _TITLE_OPEN_RE.match(text, i)
    if not title:
        return None
    line = text.count("\n", 0, title.end())
    if not line:
        return None
    # The title may sit on its own line with the `{ tag: [...] }` option and callback below it:
    # keep folding to the callback line, like a plain wrapped head.
    if _CALLBACK_RE.search(_STRING_RE.sub("''", lines[start + line])):
        return start + line
    return _head_end(lines, start + line) or start + line


def _quoted_end(text: str, i: int) -> int | None:
    """End (exclusive) of the string/template literal opening at ``i``, else ``None``."""
    quote, j, n = text[i], i + 1, len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
        elif text[j] == quote:
            return j + 1
        elif text[j] == "\n" and quote != "`":  # only a template literal may span lines
            return None
        else:
            j += 1
    return None


def _head_end(lines: list[str], start: int) -> int | None:
    """Index of the callback line closing the head opened at ``start``, or ``None``."""
    for j in range(start + 1, min(len(lines), start + 1 + _MAX_HEAD_LINES)):
        nxt = lines[j].strip()
        if nxt.startswith(("//", "/*", "*")):
            return None
        if _CALLBACK_RE.search(_STRING_RE.sub("''", nxt)):
            return j
    return None


def _mark_calls(value: ast.expr) -> list[ast.expr]:
    """The mark expressions of a ``pytestmark`` value (one mark, or a list/tuple of them)."""
    if isinstance(value, (ast.List, ast.Tuple)):
        return list(value.elts)
    return [value]


def _hits_for(decs: list[ast.expr], tests: list[str], grammar) -> tuple[list, list]:
    hits: list = []
    invalid: list = []
    for dec in decs:
        if not grammar._is_covers_marker(dec):
            continue
        for arg in dec.args:
            for test in tests:
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                    invalid.append(grammar.InvalidTag(raw=ast.dump(arg), test=test, reason="non_string_arg"))
                    continue
                parsed = grammar.canonical_fr_ac(arg.value)
                if parsed:
                    hits.append(grammar.TagHit(parsed[0], test, "pytest_marker", arg.value, parsed[1]))
                else:
                    reason = "non_canonical_ac_id" if "/" in arg.value else "non_canonical_fr_id"
                    invalid.append(grammar.InvalidTag(raw=arg.value, test=test, reason=reason))
    return hits, invalid


def _test_names(body: list[ast.stmt]) -> list[str]:
    """The ``test*`` functions pytest collects from ``body``: its own functions plus the
    methods of nested ``Test*`` classes (never a helper class's methods or a nested def)."""
    names: list[str] = []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            names += _test_names(node.body)
    return names


def python_scope_marks(source: str, path: str, grammar) -> tuple[list, list]:
    """``(hits, invalid)`` for class-level and module-level ``covers`` marks."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []
    hits: list = []
    invalid: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test") and node.decorator_list:
            tests = [f"{path}::{n}" for n in _test_names(node.body)]
            h, iv = _hits_for(node.decorator_list, tests, grammar)
            hits += h
            invalid += iv
    for stmt in tree.body:
        targets = stmt.targets if isinstance(stmt, ast.Assign) else []
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets):
            tests = [f"{path}::{n}" for n in _test_names(tree.body)]
            h, iv = _hits_for(_mark_calls(stmt.value), tests, grammar)
            hits += h
            invalid += iv
    return hits, invalid


def parse_file(rel_path: str, source: str, grammar):
    """``(source, result, scope_hits, scope_invalid)`` for one test file.

    ``source`` is returned because a TS/JS file is enumerated from its JOINED form — the
    untagged inventory must see the same declarations the tag parser saw. A leading UTF-8 BOM
    is dropped: ``ast.parse`` rejects it, which used to hide every test in such a file."""
    source = source[1:] if source.startswith("\ufeff") else source
    if rel_path.lower().endswith(grammar._TS_SUFFIXES):
        source = join_multiline_decls(source, rel_path.lower().endswith(_JSX_SUFFIXES))
    res = grammar.parse_source(rel_path, source)
    scope_hits, scope_invalid = propagate_suite_tags(source, rel_path, grammar)
    if rel_path.lower().endswith(".py"):
        h, iv = python_scope_marks(source, rel_path, grammar)
        scope_hits, scope_invalid = scope_hits + h, scope_invalid + iv
    seen = {(h.test, h.fr_id, h.ac_id) for h in res.hits}
    unique = []
    for h in scope_hits:
        key = (h.test, h.fr_id, h.ac_id)
        if key not in seen:
            seen.add(key)
            unique.append(h)
    return source, res, unique, scope_invalid


__all__ = ["join_multiline_decls", "parse_file", "python_scope_marks"]

"""Test identity for the test-tag gate: normalised body digests and "is it a test".

The traceability manifest identifies a test as ``<file>::<name>`` (Python: the function
name; TS/JS: the ``test(``/``it(`` title). That is function-level identity, never the
pytest node id, so adding a parametrize case or a class-level mark never creates a "new"
test. What the manifest cannot say is whether a test that shows up under a new id is a
MOVE of an existing one, or whether a legacy untagged test was EDITED. Both questions are
answered here by a normalised digest of the test's body:

* **Python** — the ``ast`` dump of the function's arguments and body. The leading
  docstring is dropped and comments never reach the AST, so a docstring- or comment-only
  edit digests the same. The name and the decorators are excluded: a rename keeps its
  digest (so it is matched as a move) and a new parametrize case or mark is not a body
  edit.
* **TS/JS** — the token stream of the call after the title (comments stripped, every
  run of whitespace collapsed), up to the call's closing parenthesis.

:func:`mechanically_renamed` decides the one edit the ``mechanical-refactor`` exemption may
cover: equal shapes once identifiers are anonymised, AND a one-to-one rename mapping.

Every digest function returns ``None`` for an unparseable file and ``()`` when no test of
that name is declared, so a caller can tell "could not look" from "not there".
"""

from __future__ import annotations

import ast
import copy
import hashlib
import re
from functools import lru_cache

__all__ = ["body_digests", "mechanically_renamed", "would_collect"]

_PY = (".py",)
_TS = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")
_TS_TOKEN_RE = re.compile(
    r"//[^\n]*|/\*.*?\*/"                      # comments (dropped)
    r"|(?P<str>'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`)"
    r"|(?P<id>[A-Za-z_$][\w$]*)"
    r"|(?P<num>\d[\w.]*)"
    r"|(?P<ws>\s+)"
    r"|(?P<punct>.)",
    re.DOTALL,
)
_TS_KEYWORDS = frozenset({
    "async", "await", "const", "let", "var", "function", "return", "if", "else", "for",
    "while", "of", "in", "new", "true", "false", "null", "undefined", "throw", "try",
    "catch", "finally", "typeof", "instanceof", "this", "class", "extends", "import",
    "export", "from", "default", "break", "continue", "switch", "case", "do", "void",
})


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Anonymise(ast.NodeTransformer):
    """Map every identifier to ``_`` so only the code's SHAPE survives; ``seen`` keeps the
    replaced names in visit order, so two equal shapes can be checked for a CONSISTENT rename."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def _take(self, name: str | None) -> str | None:
        if name is None:
            return None
        self.seen.append(name)
        return "_"

    def visit_Name(self, node: ast.Name) -> ast.AST:
        node.id = self._take(node.id) or "_"
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.arg = self._take(node.arg) or "_"
        node.annotation = None
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        node.attr = self._take(node.attr) or "_"
        return node

    def visit_keyword(self, node: ast.keyword) -> ast.AST:
        self.generic_visit(node)
        node.arg = self._take(node.arg)
        return node

    def visit_alias(self, node: ast.alias) -> ast.AST:
        node.name, node.asname = self._take(node.name) or "_", self._take(node.asname)
        return node


def _py_body(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(fn.body)
    first = body[0] if body else None
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        body = body[1:]
    return body


@lru_cache(maxsize=32)
def _parse(text: str) -> ast.Module | None:
    """One parse per file text: a changed file is asked about every test it holds. Callers
    only read the shared tree; anything they transform is deep-copied first."""
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


def _py_shapes(text: str, name: str, anonymise: bool) -> list[tuple[str, list[str]]] | None:
    """``[(digest, identifiers)]`` per function named ``name``; identifiers only when anonymised."""
    tree = _parse(text)
    if tree is None:
        return None
    out: list[tuple[str, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            args = copy.deepcopy(node.args)
            body = ast.Module(body=[copy.deepcopy(s) for s in _py_body(node)], type_ignores=[])
            anon = _Anonymise()
            if anonymise:
                args, body = anon.visit(args), anon.visit(body)
            out.append((_sha(ast.dump(args) + "|" + ast.dump(body)), anon.seen))
    return out


def _ts_call_tail(text: str, start: int) -> str | None:
    """Text from ``start`` up to the close paren of the call ``start`` is inside."""
    depth = 1
    for m in _TS_TOKEN_RE.finditer(text, start):
        ch = m.group("punct")
        if ch in ("(", "[", "{"):
            depth += 1
        elif ch in (")", "]", "}"):
            depth -= 1
            if depth == 0:
                return text[start:m.start()]
    return None


def _ts_normalise(chunk: str, anonymise: bool) -> tuple[str, list[str]]:
    tokens: list[str] = []
    seen: list[str] = []
    for m in _TS_TOKEN_RE.finditer(chunk):
        if m.group("ws") is not None or m.group(0).startswith(("//", "/*")):
            continue
        tok = m.group(0)
        if anonymise and m.group("id") and tok not in _TS_KEYWORDS:
            seen.append(tok)
            tok = "ID"
        tokens.append(tok)
    # A trailing comma is formatter noise (Prettier adds one when it wraps a call).
    kept = [t for i, t in enumerate(tokens) if not (t == "," and (i + 1 == len(tokens) or tokens[i + 1] in ")]}"))]
    return " ".join(kept), seen


def _ts_shapes(text: str, title: str, anonymise: bool) -> list[tuple[str, list[str]]]:
    decl = re.compile(r"\b(?:it|test)(?:\.(?!describe\b)\w+)?\s*\(\s*(['\"`])" + re.escape(title) + r"\1")
    out: list[tuple[str, list[str]]] = []
    for m in decl.finditer(text):
        tail = _ts_call_tail(text, m.end())
        if tail is not None:
            norm, seen = _ts_normalise(tail, anonymise)
            out.append((_sha(norm), seen))
    return out


def _shapes(text: str, path: str, name: str, anonymise: bool) -> list[tuple[str, list[str]]] | None:
    text = text[1:] if text.startswith("\ufeff") else text  # a UTF-8 BOM is not code
    low = path.lower()
    if low.endswith(_PY):
        return _py_shapes(text, name, anonymise)
    if low.endswith(_TS):
        return _ts_shapes(text, name, anonymise)
    return None


def body_digests(text: str, path: str, name: str) -> tuple[str, ...] | None:
    """Normalised digests of every test named ``name`` declared in ``text``.

    ``None`` = the file could not be parsed (or is not a test language); ``()`` = no such
    test. A tuple because the manifest's function-level id can name two methods of the
    same name in different classes; they are compared as one sorted set."""
    shapes = _shapes(text, path, name, False)
    return None if shapes is None else tuple(sorted(d for d, _ids in shapes))


def _bijective(before: list[str], after: list[str]) -> bool:
    forward: dict[str, str] = {}
    backward: dict[str, str] = {}
    for old, new in zip(before, after):
        if forward.setdefault(old, new) != new or backward.setdefault(new, old) != old:
            return False
    return len(before) == len(after)


def mechanically_renamed(base_text: str, head_text: str, path: str, name: str) -> bool:
    """True when every test ``name`` differs from base ONLY by a consistent identifier rename.

    The shapes must be equal with identifiers anonymised, AND the identifiers must map
    one-to-one in both directions at every occurrence. That refuses a swap at one call site
    (``f(a, b)`` -> ``f(b, a)``), a rename onto a name already in use, and any change of
    literals or structure, while a fixture or import renamed throughout still passes."""
    before, after = _shapes(base_text, path, name, True), _shapes(head_text, path, name, True)
    if not before or not after or len(before) != len(after):
        return False
    pairs = zip(sorted(before), sorted(after))
    return all(bd == hd and _bijective(bids, hids) for (bd, bids), (hd, hids) in pairs)


def _is_fixture(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if (isinstance(target, ast.Attribute) and target.attr == "fixture") or (
            isinstance(target, ast.Name) and target.id == "fixture"
        ):
            return True
    return False


def would_collect(text: str, path: str, name: str) -> bool:
    """Would pytest collect a function called ``name`` in this file as a test?

    True for a module-level ``test*`` function or a ``test*`` method of a module-level
    ``Test*`` class, unless it is a fixture. False for a fixture, a nested helper, or a
    method of a non-``Test*`` class — the shapes the ``fixture-or-helper`` exemption is
    for (and a ``Test*`` class with an ``__init__``, which pytest refuses to collect).
    Every TS/JS ``test(``/``it(`` declaration IS a test (True); an unparseable file answers
    True, so the exemption fails closed. Known limit: a project that customises
    ``python_functions``/``python_classes`` is judged by pytest's DEFAULT patterns."""
    if not path.lower().endswith(_PY):
        return True
    tree = _parse(text[1:] if text.startswith("\ufeff") else text)
    if tree is None:
        return True
    for node in tree.body:
        candidates: list[ast.stmt] = [node]
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            candidates = list(node.body)
            if any(isinstance(m, ast.FunctionDef) and m.name == "__init__" for m in candidates):
                candidates = []  # pytest refuses to collect a Test* class with an __init__
        for fn in candidates:
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == name:
                if name.startswith("test") and not _is_fixture(fn):
                    return True
    return False

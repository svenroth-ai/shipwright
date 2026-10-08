"""TS/JS half of the test-tag gate's identity: declarations, body tokens, rename bindings, tags.

A test is a ``test(``/``it(`` call (optionally with a modifier such as ``.only``/``.skip``)
whose first argument is the title literal. ``test.describe``, ``test.step`` and the hook and
fixture calls (``beforeEach``/``afterEach``/``beforeAll``/``afterAll``/``use``/``extend``) are
not tests, and a line that starts as a comment declares nothing - the same rules as
``fr_tag_grammar._TEST_DECL_RE``, the collector's enumeration matcher, so the gate never looks
for a declaration the manifest does not list.

The body is the token stream of the call after the title (comments dropped, whitespace
collapsed) up to the call's closing parenthesis. For ``mechanical-refactor`` only BINDINGS
are anonymised: callback parameters (fixtures), ``const``/``let``/``var`` names and
destructuring targets, ``function`` and ``catch`` names. A property (``resp.ok``), an object
key and any name the test does not bind (``expect``, an imported helper) must stay identical.

A data-driven ``it.each(table)('title', ...)`` / ``test.each`table`('title', ...)`` is a test
too (one id, the title text, like the collector's); its callee - modifier and table - is part of
the digest, so editing a table row or turning ``test`` into ``test.skip`` is an edit. Regex literals
and JSX are lexed by :mod:`._tag_binding_ts_lex`.
"""

from __future__ import annotations

import hashlib
import re

from ._tag_binding_ts_lex import lex

__all__ = ["ts_shapes", "ts_tag_sets"]

_NOT_TESTS = r"(?:describe|step|beforeEach|afterEach|beforeAll|afterAll|use|extend)\b"
#: ``.each(table)`` / ``.each`table``: the table is lazily bounded so a multi-line array or
#: template table reaches the call that follows it (the title quote anchors the match).
_EACH = r"(?:\.each\s*(?:\([\s\S]{0,20000}?\)|`[^`]{0,20000}?`))"
_CALLEE = (r"(?P<callee>\b(?:it|test)(?:\.(?!" + _NOT_TESTS + r"|each\b)\w+)?" + _EACH + r"?)"
           r"\s*\(\s*(?P<q>['\"`])")
_KEYWORDS = frozenset({
    "async", "await", "const", "let", "var", "function", "return", "if", "else", "for",
    "while", "of", "in", "new", "true", "false", "null", "undefined", "throw", "try",
    "catch", "finally", "typeof", "instanceof", "this", "class", "extends", "import",
    "export", "from", "default", "break", "continue", "switch", "case", "do", "void",
})
_DECLARE = frozenset({"const", "let", "var"})
_OPEN, _CLOSE = ("(", "[", "{"), (")", "]", "}")
_JSX_SUFFIXES = (".tsx", ".jsx", ".js")
_STR_RE = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")
_CALLBACK_RE = re.compile(r"=>|\bfunction\b")
_TAG_ARRAY_RE = re.compile(r"tag\s*:\s*\[([^\]]*)\]")
_COVERS_RE = re.compile(r"//\s*@covers\s+([^\n]+)")
_FR_RE = re.compile(r"FR-\d{2}\.\d{2}(?:/AC\d+)?(?![\w.-])")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _table_is_own(callee: str, jsx: bool) -> bool:
    """Is the ``.each`` table in ``callee`` exactly ONE argument that closes at the callee's end?
    The lazy table pattern would otherwise run from an earlier ``.each`` call to a later title."""
    idx = callee.find(".each")
    if idx == -1:
        return True
    table = callee[idx + len(".each"):].strip()
    if table.startswith("`"):
        return table.count("`") == 2 and table.endswith("`")
    toks, close = lex(table, 1, jsx, stop=True)
    return table.startswith("(") and close == len(table) - 1


def _decls(text: str, title: str, jsx: bool = True):
    """Declarations titled ``title``; a candidate whose ``.each`` table spans past its own closing
    paren (an earlier test's table running into a later title) is skipped and the scan resumes on the
    next line."""
    pattern = re.compile(
        r"(?m)^(?!\s*(?://|/\*|\*))[^\n]*?" + _CALLEE + re.escape(title) + r"(?P=q)")
    bare = re.compile(_CALLEE + re.escape(title) + r"(?P=q)")
    pos = 0
    while (m := pattern.search(text, pos)):
        while m and not _table_is_own(m.group("callee"), jsx):
            # Run-on from an earlier test: retry later on the same line (a second test may sit there).
            nl = text.find("\n", m.start())
            nl = len(text) if nl == -1 else nl
            nxt = bare.search(text, m.start("callee") + 1, nl)
            if not nxt:
                pos = nl + 1
            m = nxt
        if m is None:
            continue
        yield m
        pos = m.end()


def _call_tail(text: str, start: int, jsx: bool) -> str | None:
    """Text from ``start`` up to the close paren of the call ``start`` is inside."""
    toks, end = lex(text, start, jsx, stop=True)
    return text[start:end] if end < len(text) and text[end] == ")" else None


def _tokens(chunk: str, jsx: bool) -> list[tuple[bool, str]]:
    """``(is_identifier, text)`` per significant token."""
    return [(t.kind == "id", " ".join(t.text.split()) if t.kind == "jsx" else t.text)
            for t in lex(chunk, 0, jsx)[0]]


def _close(toks: list[tuple[bool, str]], i: int) -> int:
    depth = 0
    for j in range(i, len(toks)):
        depth += toks[j][1] in _OPEN
        depth -= toks[j][1] in _CLOSE
        if depth == 0:
            return j
    return len(toks) - 1


def _pattern_ids(toks: list[tuple[bool, str]], lo: int, hi: int) -> set[str]:
    """Names a parameter list / destructuring pattern binds: at the top level every name
    up to a ``:`` type or ``=`` default; inside ``{}``/``[]`` a name that is not a key."""
    ids: set[str] = set()
    depth, skipping = 0, False
    for i in range(lo, hi):
        is_id, t = toks[i]
        if t in _OPEN:
            depth += 1
        elif t in _CLOSE:
            depth -= 1
        elif depth == 0:
            if t == ",":
                skipping = False
            elif t in (":", "="):
                skipping = True
            elif is_id and not skipping:
                ids.add(t)
        elif is_id and not skipping and toks[i - 1][1] in ("{", "[", ",", ":", "...") and (
                i + 1 >= len(toks) or toks[i + 1][1] != ":"):
            ids.add(t)
    return ids


def _bound(toks: list[tuple[bool, str]]) -> set[str]:
    bound: set[str] = set()
    for i, (is_id, t) in enumerate(toks):
        prev = toks[i - 1][1] if i else ""
        nxt = toks[i + 1][1] if i + 1 < len(toks) else ""
        if is_id and (prev in _DECLARE or prev in ("function", "class") or nxt == "=>"):
            bound.add(t)
        elif t in _DECLARE and nxt in ("{", "["):
            bound |= _pattern_ids(toks, i + 1, _close(toks, i + 1) + 1)
        elif t == "(":
            j = _close(toks, i)
            after = toks[j + 1][1] if j + 1 < len(toks) else ""
            before = {prev, toks[i - 2][1] if i > 1 else ""}
            if after == "=>" or "function" in before or prev == "catch":
                bound |= _pattern_ids(toks, i + 1, j)
    return bound - _KEYWORDS


def _is_key_or_member(toks: list[tuple[bool, str]], i: int) -> bool:
    prev = toks[i - 1][1] if i else ""
    nxt = toks[i + 1][1] if i + 1 < len(toks) else ""
    return prev == "." or (prev in ("{", ",") and nxt == ":")


def _normalise(chunk: str, anonymise: bool, jsx: bool) -> tuple[str, list[str]]:
    toks = _tokens(chunk, jsx)
    bound = _bound(toks) if anonymise else set()
    out: list[str] = []
    seen: list[str] = []
    for i, (is_id, t) in enumerate(toks):
        if is_id and t in bound and not _is_key_or_member(toks, i):
            seen.append(t)
            t = "ID"
        out.append(t)
    # A trailing comma is formatter noise (Prettier adds one when it wraps a call).
    kept = [t for i, t in enumerate(out) if not (t == "," and (i + 1 == len(out) or out[i + 1] in _CLOSE))]
    return " ".join(kept), seen


def ts_shapes(text: str, title: str, anonymise: bool, path: str = "") -> list[tuple[str, list[str]]]:
    """``[(digest, bound names)]`` per declaration titled ``title``. The digest covers the
    callee (``test.skip``, an ``.each`` table) and the call after the title; ``path`` decides
    whether JSX is lexed (not in a ``.ts`` file, where ``<T>x`` is a type assertion)."""
    jsx = not path or path.lower().endswith(_JSX_SUFFIXES)
    out: list[tuple[str, list[str]]] = []
    for m in _decls(text, title, jsx):
        tail = _call_tail(text, m.end(), jsx)
        if tail is not None:
            callee, _ = _normalise(re.sub(r"^it(?![\w$])", "test", m.group("callee")), False, jsx)
            norm, seen = _normalise(tail, anonymise, jsx)
            out.append((_sha(callee + " | " + norm), seen))
    return out


def ts_tag_sets(text: str, title: str) -> list[frozenset[str]]:
    """The requirement ids each declaration titled ``title`` carries itself: its ``tag:``
    array (in the head, before the callback), a title suffix and a ``// @covers`` on its own
    line or the line before. A ``describe``-level tag is not counted, so a sibling relying on
    one reads as untagged - the conservative side for the ``ambiguous-name`` rule."""
    out: list[set[str]] = []
    for m in _decls(text, title):
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        prev_start = text.rfind("\n", 0, max(line_start - 1, 0)) + 1
        prev = text[prev_start:line_start] if line_start else ""
        head = text[m.end():m.end() + 2000]
        blanked = _STR_RE.sub(lambda s: "'" + " " * (len(s.group(0)) - 2) + "'", head)
        cb = _CALLBACK_RE.search(blanked)
        head = head[:cb.start()] if cb else head
        found = set(_FR_RE.findall(" ".join(_TAG_ARRAY_RE.findall(head)) + " " + title))
        own_line = text[line_start:line_end if line_end != -1 else len(text)]
        for chunk in [own_line] + ([prev] if prev.strip().startswith("//") else []):
            for ids in _COVERS_RE.findall(chunk):
                found |= set(_FR_RE.findall(ids))
        out.append(found)
    return [frozenset(s) for s in out]

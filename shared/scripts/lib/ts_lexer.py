"""Lexer for TS/JS test sources: strings, templates, comments, regex literals, JSX.

Shared by the test-tag gate (``tools.verifiers._tag_binding_ts``) and the compliance collector
(``_file_tags``), so a wrapped ``.each`` table is closed at the same paren by both. Stdlib only.

The gate compares a test's body as a token stream (``_tag_binding_ts``). A regex-only tokenizer
reads a quote inside a regex literal (``/it's/``) or inside JSX text (``<p>Don't</p>``) as the
start of a string, which swallows the rest of the body and shifts every later token: a real
edit can then digest the same, and an untouched body can digest differently. This lexer knows
those two shapes.

* **regex literal** - a ``/`` where an expression may start (after an operator, an opening
  bracket, a separator or a keyword such as ``return``), never after an identifier, number,
  string, ``)`` or ``]`` (those make it a division). A ``[...]`` class may hold an unescaped ``/``.
* **JSX** - an element where an expression may start and a tag name follows ``<`` (``.tsx``,
  ``.jsx``, ``.js``; never ``.ts``, where ``<T>x`` is a type assertion). Tags and text become
  ``jsx`` tokens (text whitespace-collapsed, so a quote in it is just text); ``{expr}`` children and
  attributes are lexed as code, so identifiers inside them stay visible to the rename check. An
  element that does not close is not JSX: the ``<`` falls back to a punctuation token.

Known limit: ``/`` after ``}`` or ``)`` is judged by the last token only (``if (x) /re/.test(y)``
reads as a division).
"""

from __future__ import annotations

import re
from typing import NamedTuple

__all__ = ["Tok", "lex"]


#: Start offsets of a template / element already known NOT to close, for the outermost ``lex`` call in
#: progress. A failed nested attempt falls back to plain tokens and re-lexes the same suffix; without
#: this memo an unclosed ``${`${`${...`` or ``<b>{<b>{...`` doubles the work at every level.
_DEAD: set[tuple[str, int]] = set()
_DEPTH = [0]


class Tok(NamedTuple):
    kind: str  # id | num | str | regex | jsx | punct
    text: str
    start: int
    end: int


_ID_RE = re.compile(r"[A-Za-z_$][\w$]*")
_NUM_RE = re.compile(r"\d[\w.]*")
_WS_RE = re.compile(r"\s+")
_JSX_NAME_RE = re.compile(r"[A-Za-z_$][\w$.:-]*")
_ATTR_RE = re.compile(r"[A-Za-z_$][\w$:-]*")
_OPEN, _CLOSE = "([{", ")]}"
#: Keywords after which an expression (so a regex or an element) may start.
_EXPR_KEYWORDS = frozenset({
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw", "case",
    "do", "else", "yield", "await",
})
_REGEX_FLAGS_RE = re.compile(r"[a-z]*")


def _expr_may_start(prev: Tok | None) -> bool:
    if prev is None:
        return True
    if prev.kind == "id":
        return prev.text in _EXPR_KEYWORDS
    if prev.kind == "punct":
        return prev.text not in (")", "]")
    return False


def _string_end(text: str, i: int) -> int | None:
    """End (exclusive) of the ``'``/``"`` string opening at ``i`` on its own line, else ``None``."""
    quote, j, n = text[i], i + 1, len(text)
    while j < n:
        ch = text[j]
        if ch == "\\":
            j += 2
        elif ch == quote:
            return j + 1
        elif ch == "\n":
            return None
        else:
            j += 1
    return None


def _template_end(text: str, i: int, jsx: bool) -> int | None:
    if ("t", i) in _DEAD:
        return None
    end = _template_end_raw(text, i, jsx)
    if end is None:
        _DEAD.add(("t", i))
    return end


def _template_end_raw(text: str, i: int, jsx: bool) -> int | None:
    """End (exclusive) of the template literal opening at ``i``; ``${...}`` may nest anything."""
    j, n = i + 1, len(text)
    while j < n:
        ch = text[j]
        if ch == "\\":
            j += 2
        elif ch == "`":
            return j + 1
        elif ch == "$" and text.startswith("${", j):
            _toks, close = lex(text, j + 2, jsx, stop=True)
            if close >= n or text[close] != "}":
                return None
            j = close + 1
        else:
            j += 1
    return None


def _regex_end(text: str, i: int) -> int | None:
    """End (exclusive, flags included) of the regex literal opening at ``i``, else ``None``."""
    j, n, in_class = i + 1, len(text), False
    while j < n:
        ch = text[j]
        if ch == "\n":
            return None
        if ch == "\\":
            j += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            return _REGEX_FLAGS_RE.match(text, j + 1).end()
        j += 1
    return None


def _skip_ws_comments(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        if text[i].isspace():
            i = _WS_RE.match(text, i).end()
        elif text.startswith("//", i):
            nl = text.find("\n", i)
            i = n if nl == -1 else nl
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                return n
            i = end + 2
        else:
            break
    return i


def _jsx_expr(text: str, i: int, out: list[Tok]) -> int | None:
    """Lex the ``{...}`` expression at ``i`` into ``out`` (braces included); end or ``None``."""
    toks, close = lex(text, i + 1, True, stop=True)
    if close >= len(text) or text[close] != "}":
        return None
    out.append(Tok("punct", "{", i, i + 1))
    out.extend(toks)
    out.append(Tok("punct", "}", close, close + 1))
    return close + 1


def _jsx_attrs(text: str, i: int, out: list[Tok]) -> tuple[int, bool] | None:
    """Lex tag attributes from ``i``; ``(index after the tag, self_closing)`` or ``None``."""
    n = len(text)
    while True:
        i = _skip_ws_comments(text, i)
        if i >= n:
            return None
        if text.startswith("/>", i):
            out.append(Tok("jsx", "/>", i, i + 2))
            return i + 2, True
        if text[i] == ">":
            out.append(Tok("jsx", ">", i, i + 1))
            return i + 1, False
        if text[i] == "{":  # {...spread}
            i = _jsx_expr(text, i, out)
            if i is None:
                return None
            continue
        m = _ATTR_RE.match(text, i)
        if not m:
            return None
        out.append(Tok("jsx", m.group(0), i, m.end()))
        i = _skip_ws_comments(text, m.end())
        if i < n and text[i] == "=":
            out.append(Tok("jsx", "=", i, i + 1))
            i = _skip_ws_comments(text, i + 1)
            if i >= n:
                return None
            if text[i] in "'\"":  # JSX attribute strings have no escapes and may span lines
                end = text.find(text[i], i + 1)
                if end == -1:
                    return None
                out.append(Tok("str", text[i:end + 1], i, end + 1))
                i = end + 1
            elif text[i] == "{":
                i = _jsx_expr(text, i, out)
                if i is None:
                    return None
            elif text[i] == "<":
                inner = _jsx_element(text, i)
                if inner is None:
                    return None
                out.extend(inner[0])
                i = inner[1]
            else:
                return None


def _jsx_element(text: str, i: int) -> tuple[list[Tok], int] | None:
    if ("j", i) in _DEAD:
        return None
    result = _jsx_element_raw(text, i)
    if result is None:
        _DEAD.add(("j", i))
    return result


def _jsx_element_raw(text: str, i: int) -> tuple[list[Tok], int] | None:
    """Lex the element (or fragment) opening at ``i``; ``(tokens, end)`` or ``None``."""
    n = len(text)
    out: list[Tok] = [Tok("jsx", "<", i, i + 1)]
    name = _JSX_NAME_RE.match(text, i + 1)
    j = name.end() if name else i + 1
    if name:
        out.append(Tok("jsx", name.group(0), i + 1, j))
    parsed = _jsx_attrs(text, j, out)
    if parsed is None:
        return None
    j, self_closing = parsed
    if self_closing:
        return out, j
    while j < n:
        if text.startswith("</", j):
            end = text.find(">", j)
            if end == -1:
                return None
            closing = "".join(text[j:end + 1].split())
            if closing != "</" + (name.group(0) if name else "") + ">":
                return None  # not this element's end: the opener was a generic / stray `<`
            out.append(Tok("jsx", closing, j, end + 1))
            return out, end + 1
        if text[j] == "<" and j + 1 < n and (text[j + 1] in ">_$" or text[j + 1].isalpha()):
            inner = _jsx_element(text, j)
            if inner is None:
                return None
            out.extend(inner[0])
            j = inner[1]
        elif text[j] == "{":
            j = _jsx_expr(text, j, out)
            if j is None:
                return None
        else:
            k = j + 1
            while k < n and text[k] not in "<{":
                k += 1
            chunk = text[j:k]
            if chunk.strip():
                out.append(Tok("jsx", " ".join(chunk.split()), j, k))
            j = k
    return None


def lex(text: str, start: int = 0, jsx: bool = True, stop: bool = False) -> tuple[list[Tok], int]:
    """``(tokens, end)``: significant tokens only (no whitespace, no comments).

    ``stop`` ends at the first closing bracket that has no opener in the lexed span (its index is
    returned, unconsumed); otherwise the whole text is lexed and ``end`` is ``len(text)``."""
    if not _DEPTH[0]:
        _DEAD.clear()
    _DEPTH[0] += 1
    try:
        return _lex(text, start, jsx, stop)
    finally:
        _DEPTH[0] -= 1


def _lex(text: str, start: int, jsx: bool, stop: bool) -> tuple[list[Tok], int]:
    toks: list[Tok] = []
    i, n, depth = start, len(text), 0
    prev: Tok | None = None
    while i < n:
        i = _skip_ws_comments(text, i)
        if i >= n:
            break
        ch = text[i]
        tok: Tok | None = None
        if ch in "'\"":
            end = _string_end(text, i)
            tok = Tok("str", text[i:end], i, end) if end else Tok("punct", ch, i, i + 1)
        elif ch == "`":
            end = _template_end(text, i, jsx)
            tok = Tok("str", text[i:end], i, end) if end else Tok("punct", ch, i, i + 1)
        elif ch == "/" and _expr_may_start(prev):
            end = _regex_end(text, i)
            tok = Tok("regex", text[i:end], i, end) if end else Tok("punct", ch, i, i + 1)
        elif ch == "<" and jsx and _expr_may_start(prev) and i + 1 < n and (
                text[i + 1] in ">_$" or text[i + 1].isalpha()):
            element = _jsx_element(text, i)
            if element:
                toks.extend(element[0])
                prev = Tok("jsx", "", i, element[1])
                i = element[1]
                continue
            tok = Tok("punct", ch, i, i + 1)
        elif (m := _ID_RE.match(text, i)):
            tok = Tok("id", m.group(0), i, m.end())
        elif (m := _NUM_RE.match(text, i)):
            tok = Tok("num", m.group(0), i, m.end())
        else:
            width = 2 if text.startswith("=>", i) else 3 if text.startswith("...", i) else 1
            tok = Tok("punct", text[i:i + width], i, i + width)
            if tok.text in _OPEN:
                depth += 1
            elif tok.text in _CLOSE:
                if stop and depth == 0:
                    return toks, i
                depth -= 1
        toks.append(tok)
        prev = tok
        i = tok.end
    return toks, n

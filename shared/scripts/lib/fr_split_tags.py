"""The test-tag half of ``fr_split``: re-point the tags that bind a moved criterion to its new id (atomic-frs U2).

Only places that really BIND are rewritten, exactly the ones :mod:`lib.fr_cluster_evidence` reads as evidence - the string
arguments of a ``covers(...)`` decorator or ``pytestmark`` value, and comments (``#`` in Python, ``//`` and ``/* */`` in
JS/TS). The text of any other string literal (fixture data that merely mentions an id) is left alone. Both ``FR-01.11/AC21``
and ``FR-01.11.AC21`` are rewritten, keeping the separator. A bare ``FR-01.11`` tag (FR-level) is never touched.
Pure and stdlib only: ``rewrite_tags(rel, text, moves)`` returns the new text.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize

from lib.fr_cluster_evidence import js_comment_spans

__all__ = ["rewrite_tags"]

_REF = re.compile(r"(FR-\d+\.\d+)([./])AC(\d+)(?!\d)")


def _sub(segment: str, moves: dict[str, str]) -> str:
    def one(m: re.Match) -> str:
        new = moves.get(f"{m.group(1)}/AC{int(m.group(3)):02d}")
        if not new:
            return m.group(0)
        fr, ac = new.split("/AC")
        return f"{fr}{m.group(2)}AC{ac}"
    return _REF.sub(one, segment)


def _offsets(text: str) -> list[int]:
    out, pos = [], 0
    for ln in text.split("\n"):  # NOT splitlines(): ast and tokenize count only \n / \r\n as line breaks
        out.append(pos)
        pos += len(ln) + 1
    return out


def _abs(text: str, starts: list[int], line: int, byte_col: int) -> int:
    """Absolute char offset of an ``ast`` position (its column counts UTF-8 bytes)."""
    row = text[starts[line - 1]:].split("\n", 1)[0]
    return starts[line - 1] + len(row.encode("utf-8")[:byte_col].decode("utf-8", "ignore"))


def _py_spans(text: str) -> list[tuple[int, int]]:
    try:
        tree = ast.parse(text)
        comments = [t for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type == tokenize.COMMENT]
    except (SyntaxError, tokenize.TokenError, ValueError):
        return []
    starts = _offsets(text)
    spans = [(starts[t.start[0] - 1] + t.start[1], starts[t.end[0] - 1] + t.end[1]) for t in comments]
    roots: list[ast.expr] = []

    def covers_calls(expr: ast.expr) -> list[ast.expr]:
        """Only the ``covers(...)`` calls themselves: a ``parametrize`` row that merely mentions the word is test input, not a tag."""
        return [n for n in ast.walk(expr) if isinstance(n, ast.Call)
                and (getattr(n.func, "attr", None) == "covers" or getattr(n.func, "id", None) == "covers")]

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for d in node.decorator_list:
                roots += covers_calls(d)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            roots += covers_calls(node.value)
    for r in roots:
        for n in ast.walk(r):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.end_lineno is not None and n.end_col_offset is not None:
                spans.append((_abs(text, starts, n.lineno, n.col_offset), _abs(text, starts, n.end_lineno, n.end_col_offset)))
    return spans


def _rewrite_js(text: str, moves: dict[str, str]) -> str:
    out, state = [], ""
    for line in text.splitlines(keepends=True):
        spans, state = js_comment_spans(line, state)
        for s, e in reversed(spans):
            line = line[:s] + _sub(line[s:e], moves) + line[e:]
        out.append(line)
    return "".join(out)


def rewrite_tags(rel: str, text: str, moves: dict[str, str]) -> str:
    """``text`` with every binding tag of a moved criterion (``moves``: ``{"FR-01.11/AC21": "FR-01.22/AC21"}``) re-pointed."""
    if not any(old.split("/")[0] in text for old in moves):
        return text
    if not rel.endswith(".py"):
        return _rewrite_js(text, moves)
    for s, e in sorted(set(_py_spans(text)), reverse=True):
        text = text[:s] + _sub(text[s:e], moves) + text[e:]
    return text

"""Suite/``describe``-level ``@FR`` propagation for the ``test_links`` collector (TT1 AC2).

The frozen ``fr_tag_grammar`` reference parser binds ``it()``/``test()`` only — a tag on
a ``describe``/suite is a *production-collector* feature (its own docstring says so). This
module adds it: a native ``{ tag: ['@FR-..'] }`` or a ``// @covers FR-..`` on a
``describe(`` propagates the FR to every ``it()``/``test()`` inside that describe block,
scoped by brace depth (nested describes both apply). It layers ON TOP of the per-test tags
the reference parser already returns, and reuses that parser's OWN classifiers so the
valid/malformed split never diverges from the frozen grammar.
"""

from __future__ import annotations

import re
from bisect import bisect_right

from ._lib_loader import load_shared_lib

# The gate's own lexer: braces inside string, template and regex literals and comments never count.
_lex = load_shared_lib("ts_lexer").lex
JSX_SUFFIXES = (".tsx", ".jsx", ".js")  # JSX text is lexed for these only, never for ``.ts`` (``<T>x`` is a cast)
UNBOUND_COVERS = "unbound-covers-comment"

_DESCRIBE_RE = re.compile(r"\bdescribe(?:\.\w+)?\s*\(\s*(['\"`])(?P<title>.*?)\1")
# A describe call that ends its statement on its own line: ``describe('x', () => {});``.
_CLOSED_ON_LINE_RE = re.compile(r"\{.*\}\s*\)\s*;?\s*(?://.*)?$")


def _describe_tokens(line: str, dtest: str, grammar, pending, same_line_covers, invalid):
    """Collect (fr_id, tag_source, raw) for a describe's native tag + @covers comments."""
    tokens: list[tuple[str, str, str]] = []
    arr = grammar._TAG_ARRAY_RE.search(line)
    if arr:
        h, iv = grammar._classify_at_tokens(arr.group("body"), dtest, "native_tag")
        tokens += [(x.fr_id, x.tag_source, x.raw) for x in h]
        invalid.extend(iv)
    for chunk in (pending, same_line_covers):
        if chunk is not None:
            h, iv = grammar._classify_bare_ids(chunk, dtest, "covers_comment")
            tokens += [(x.fr_id, x.tag_source, x.raw) for x in h]
            invalid.extend(iv)
    return tokens


def brace_deltas(lines: list[str], jsx: bool) -> list[int]:
    """Net ``{`` minus ``}`` per line, counted over the lexed token stream of the whole source."""
    starts, pos = [], 0
    for ln in lines:
        starts.append(pos)
        pos += len(ln) + 1
    deltas = [0] * len(lines)
    for tok in _lex("\n".join(lines), 0, jsx)[0]:
        if tok.kind == "punct" and tok.text in ("{", "}"):
            deltas[bisect_right(starts, tok.start) - 1] += 1 if tok.text == "{" else -1
    return deltas


def _unbound(grammar, path: str, lineno: int, ids: str):
    """A covers comment that reaches no declaration: reported, never rebound to a later line."""
    return grammar.InvalidTag(raw=f"{path}:{lineno}: // @covers {ids.strip()}", test="", reason=UNBOUND_COVERS)


def propagate_suite_tags(source: str, path: str, grammar, origin=None):
    """Return ``(hits, invalid)`` for describe-level tags propagated to inner tests.

    Non-TS/JS sources produce nothing: describe/it suites are a TS/JS-only construct, so a
    ``describe(...)`` / ``it(...)`` that appears only inside a PYTHON string literal (e.g. a
    collector self-test that embeds TS test-source as data) is NOT mistaken for a real suite
    tag. Safe to call on any test file — the suffix gate makes the "``.py`` yields nothing"
    contract real rather than incidental.

    Brace-depth scoped with an ``entered`` flag so a describe whose callback body
    brace lands on the FOLLOWING line (Prettier-wrapped signatures) is not popped
    before its body opens. Known limitation: a one-line ``describe(..., () => { it(...) })``
    does not propagate (describe + test share a line) — the dominant multi-line form does.

    ``origin`` = ``(deltas, linenos)`` per line of ``source`` when it is a JOINED form of the file:
    the brace delta counted on the original lines and each line's original 1-based number. Without
    it the deltas and line numbers are those of ``source`` itself.
    """
    # describe/it suites are a TS/JS-only construct — gate on the frozen grammar's OWN suffix set
    # (the single authoritative list, identical to what the collector scans) so a describe/it
    # inside a PYTHON string literal is never mistaken for a real suite tag, and no third copy of
    # the suffix vocabulary drifts.
    if not path.lower().endswith(grammar._TS_SUFFIXES):
        return [], []
    hits: list = []
    invalid: list = []
    stack: list[list] = []   # [open_depth, tokens, entered]
    pending: str | None = None           # leading // @covers ids awaiting the next line
    pending_at = 0
    depth = 0
    opened_here = False
    lines = source.splitlines()
    deltas, linenos = origin or (brace_deltas(lines, path.lower().endswith(JSX_SUFFIXES)), None)

    for lineno, line in enumerate(lines, 1):
        while stack and stack[-1][2] and depth <= stack[-1][0]:
            stack.pop()
        cm = grammar._COVERS_COMMENT_RE.search(line)
        same_line_covers = cm.group("ids") if cm else None
        describe = _DESCRIBE_RE.search(line)
        decl = grammar._TEST_DECL_RE.search(line)

        if describe and not decl:
            dtest = f"{path}::{describe.group('title')}"
            tokens = _describe_tokens(line, dtest, grammar, pending, same_line_covers, invalid)
            pending = None
            stack.append([depth, tokens, False])
            opened_here = bool(_CLOSED_ON_LINE_RE.search(line[describe.end():]))
        elif decl:
            test = f"{path}::{decl.group('title')}"
            for _open_depth, tokens, _entered in stack:
                for fr_id, tag_source, raw in tokens:
                    hits.append(grammar.TagHit(fr_id, test, tag_source, raw))
            pending = None
        elif same_line_covers is not None:
            if pending is not None:   # two covers lines in a row: the first is overwritten
                invalid.append(_unbound(grammar, path, pending_at, pending))
            pending, pending_at = same_line_covers, linenos[lineno - 1] if linenos else lineno
        else:
            if pending is not None:
                invalid.append(_unbound(grammar, path, pending_at, pending))
            pending = None

        depth += deltas[lineno - 1]
        if describe and not decl and opened_here and depth <= stack[-1][0]:
            # Body opened AND closed on this line: nothing inside to tag, never leak. The covers
            # comment above it is BOUND (to the describe, a declaration), so no unbound warning.
            stack.pop()
        for entry in stack:
            if depth > entry[0]:
                entry[2] = True   # the describe body has opened — now poppable on close

    if pending is not None:
        invalid.append(_unbound(grammar, path, pending_at, pending))
    return hits, invalid


__all__ = ["JSX_SUFFIXES", "UNBOUND_COVERS", "brace_deltas", "propagate_suite_tags"]

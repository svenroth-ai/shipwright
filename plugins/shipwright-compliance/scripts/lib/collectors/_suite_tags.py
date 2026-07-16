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

_DESCRIBE_RE = re.compile(r"\bdescribe(?:\.\w+)?\s*\(\s*(['\"`])(?P<title>.*?)\1")


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


def propagate_suite_tags(source: str, path: str, grammar):
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
    depth = 0

    for line in source.splitlines():
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
        elif decl:
            test = f"{path}::{decl.group('title')}"
            for _open_depth, tokens, _entered in stack:
                for fr_id, tag_source, raw in tokens:
                    hits.append(grammar.TagHit(fr_id, test, tag_source, raw))
            pending = None
        elif same_line_covers is not None:
            pending = same_line_covers
        else:
            pending = None

        depth += line.count("{") - line.count("}")
        for entry in stack:
            if depth > entry[0]:
                entry[2] = True   # the describe body has opened — now poppable on close

    return hits, invalid


__all__ = ["propagate_suite_tags"]

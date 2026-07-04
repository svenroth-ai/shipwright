#!/usr/bin/env python3
"""Blank out non-code token spans (strings, docstrings, comments, f-string
literals) in Python source so a line/regex scanner matches executable code
only — never token text that merely appears inside a literal or comment.

Used by ``prompt_injection_scan.scan_python`` so a security-audit test that
lists dangerous tokens as forbidden string literals is not a false positive.
Spans are replaced by spaces (not removed) so every newline and column is
preserved: reported line numbers and multi-token patterns stay accurate.
"""

from __future__ import annotations

import io
import tokenize

# Token types whose content is data / prose, not executable code.
NONCODE_TOKEN_TYPES = {tokenize.STRING, tokenize.COMMENT}
for _tok_name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
    _tok_type = getattr(tokenize, _tok_name, None)  # present on Python 3.12+
    if _tok_type is not None:
        NONCODE_TOKEN_TYPES.add(_tok_type)


def blank_noncode_spans(text: str) -> str:
    """Return ``text`` with STRING / COMMENT (and f-string literal) token spans
    replaced by spaces, preserving every newline and column.

    Falls back to the original text when the source does not tokenize (invalid
    Python) so a broken file is still scanned line-by-line rather than skipped.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError, ValueError):
        return text

    rows = [list(line) for line in text.split("\n")]
    for tok in tokens:
        if tok.type not in NONCODE_TOKEN_TYPES:
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        for row in range(srow, erow + 1):
            idx = row - 1
            if idx >= len(rows):  # pragma: no cover - defensive
                continue
            chars = rows[idx]
            start = scol if row == srow else 0
            end = ecol if row == erow else len(chars)
            for col in range(start, min(end, len(chars))):
                chars[col] = " "
    return "\n".join("".join(chars) for chars in rows)

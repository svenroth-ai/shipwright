"""Comment/string/template/regex-aware lexer for TS/JS hygiene scanning (TT4).

Extracted from ``ts_test_hygiene.py`` (kept ≤300 LOC per the bloat baseline).
``lex`` blanks every comment, string, template, and regex-literal region of a
TS/JS source to spaces — newlines preserved so char offsets still map to the
original line — so the hygiene matcher runs on *code-only* text and cannot
false-match ``test.only`` inside a comment / string / template / regex literal.

Regex literals are recognized with the standard prev-significant-token
heuristic (a ``/`` starts a regex when the previous significant code char is not
an identifier / number / ``)`` / ``]`` / ``}`` / quote). This closes two holes:
a lone backtick inside a regex (``/`/``) no longer opens a template and blanks
to EOF, and a regex body like ``/test.only(/`` is blanked (never scanned as
code). Known limit (documented, forgotten-skip threat model — not adversarial):
a regex that follows a value-returning keyword (``return /re/``) is read as
division; harmless for the skip/only matcher.

An UNTERMINATED string / template / block comment (no closing delimiter before
EOF) is recorded in ``LexResult.unterminated`` so the scanner can emit a LOUD
``could_not_lex`` finding instead of silently blanking the rest of the file —
fail-loud, never silently disable scanning.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LexResult:
    """Result of :func:`lex`.

    ``code_only`` is the blanked source; ``comments`` maps a 1-indexed line to
    its raw comment fragments (for quarantine parsing); ``unterminated`` lists
    ``(line, kind)`` for each string/template/block-comment that ran to EOF.
    """

    code_only: str
    comments: dict[int, list[str]]
    unterminated: list[tuple[int, str]] = field(default_factory=list)


def _regex_allowed(prev: str) -> bool:
    """True if a ``/`` at this position may start a regex literal.

    ``prev`` is the last significant code char. A regex is allowed at the start
    of input or after an operator/punctuator; it is division after a value
    (identifier, number, ``)``, ``]``, ``}``, or a closed quote).
    """
    if prev == "":
        return True
    return not (prev.isalnum() or prev in "_$)]}\"'`")


def _scan_regex(source: str, i: int, n: int) -> int | None:
    """Return the index just past a regex literal starting at ``source[i]=='/'``,
    or ``None`` when there is no valid single-line close (treat as division)."""
    j = i + 1
    in_class = False
    while j < n:
        c = source[j]
        if c == "\n":
            return None  # a regex literal cannot span lines → not a regex
        if c == "\\":
            j += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            j += 1
            while j < n and source[j].isalpha():  # flags (g, i, m, …)
                j += 1
            return j
        j += 1
    return None


def lex(source: str) -> LexResult:
    """Blank comments/strings/templates/regex to spaces; collect comments +
    unterminated-construct signals. See the module docstring for the contract."""
    code = list(source)
    comments: dict[int, list[str]] = {}
    unterminated: list[tuple[int, str]] = []
    n = len(source)
    i = 0
    line = 1
    last_sig = ""  # last significant (non-space) code char

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if code[k] != "\n":
                code[k] = " "

    def add(ln: int, text: str) -> None:
        comments.setdefault(ln, []).append(text)

    while i < n:
        c = source[i]
        nxt = source[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = i + 2
            while j < n and source[j] != "\n":
                j += 1
            add(line, source[i + 2 : j])
            blank(i, j)
            i = j
            continue
        if c == "/" and nxt == "*":
            j = i + 2
            while j + 1 < n and not (source[j] == "*" and source[j + 1] == "/"):
                j += 1
            closed = j + 1 < n
            end = j + 2 if closed else n
            if not closed:
                unterminated.append((line, "block comment"))
            for idx, seg in enumerate(source[i + 2 : j].split("\n")):
                add(line + idx, seg)
            blank(i, end)
            line += source[i:end].count("\n")
            i = end
            continue
        if c in ("'", '"'):
            j = i + 1
            while j < n and source[j] != c and source[j] != "\n":
                j += 2 if source[j] == "\\" else 1
            closed = j < n and source[j] == c
            end = j + 1 if closed else j
            if not closed:
                unterminated.append((line, "string"))
            blank(i, end)
            line += source[i:end].count("\n")
            last_sig = c
            i = end
            continue
        if c == "`":
            j = i + 1
            while j < n and source[j] != "`":
                j += 2 if source[j] == "\\" else 1
            closed = j < n
            end = j + 1 if closed else n
            if not closed:
                unterminated.append((line, "template"))
            blank(i, end)
            line += source[i:end].count("\n")
            last_sig = "`"
            i = end
            continue
        if c == "/" and _regex_allowed(last_sig):
            end = _scan_regex(source, i, n)
            if end is not None:
                blank(i, end)
                line += source[i:end].count("\n")
                last_sig = ")"  # a regex is a value → next `/` is division
                i = end
                continue
        if c == "\n":
            line += 1
        elif not c.isspace():
            last_sig = c
        i += 1

    return LexResult("".join(code), comments, unterminated)

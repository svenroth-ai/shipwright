"""Find the exported config array of an ESLint flat config and splice text into it.

Split out of ``eslint_architecture_rules.py`` (size). Supported shapes are a closed list:
``export default [...]``, ``export default defineConfig([...])``, ``module.exports = [...]`` and
a named const of either (``const eslintConfig = defineConfig([...]); export default eslintConfig;``,
what create-next-app writes). Everything else returns ``None`` plus a reason; a caller must then
refuse, never guess. Comments, strings, templates and regex literals are blanked by the lexer first
(same length, so offsets of the blanked text are offsets of the real text; a test pins it),
so brackets inside them do not count. Stdlib-only.
"""

from __future__ import annotations

import re

from _ts_lexer import lex

_PAIRS = {"]": "[", "}": "{", ")": "("}


def array_bounds(text: str) -> tuple:
    """((open '[' index, close ']' index), '') of the exported array, or (None, reason)."""
    lexed = lex(text)
    if lexed.unterminated:
        return None, "the file has an unterminated string, template or comment"
    code = lexed.code_only
    starts = [m.end() for m in re.finditer(r"export\s+default\s+|module\.exports\s*=\s*", code)]
    if len(starts) != 1:
        return None, f"expected one default export, found {len(starts)}"
    pos = starts[0]
    named = re.match(r"([A-Za-z_$][\w$]*)[ \t]*(?:;|\r?\n|$)", code[pos:])
    if named:
        decl = list(re.finditer(rf"\b(?:const|let|var)\s+{re.escape(named.group(1))}\s*(?::[^=;]+)?=\s*", code))
        if len(decl) != 1:
            return None, f"cannot find the one declaration of {named.group(1)}"
        pos = decl[0].end()
    wrap = re.match(r"defineConfig\s*\(\s*", code[pos:])
    if wrap:
        pos += wrap.end()
    if pos >= len(code) or code[pos] != "[":
        return None, "the exported value is not an array literal or defineConfig([...])"
    stack: list = []
    for i in range(pos, len(code)):
        ch = code[i]
        if ch in "[{(":
            stack.append(ch)
        elif ch in _PAIRS:
            if not stack or stack.pop() != _PAIRS[ch]:
                return None, "unbalanced brackets"
            if not stack:
                after = code[i + 1:].lstrip()
                if wrap:
                    if not after.startswith(")"):
                        return None, "defineConfig call has more than the one array argument"
                    after = after[1:].lstrip()
                if after[:1] in (".", "(", "[", "+", "-", "*", "/", "?"):
                    return None, "the array is used in an expression, not exported as is"
                return (pos, i), ""
    return None, "unbalanced brackets"


def live_in_array(text: str, bounds: tuple, begin: int, end: int) -> bool:
    """True when [begin, end) is real code directly inside the array (bracket depth 1, not a comment)."""
    code = lex(text).code_only
    if not code[begin:end].strip():
        return False  # commented out: the lexer blanked it
    depth = 0
    for ch in code[bounds[0]:begin]:
        depth += (ch in "[{(") - (ch in "]})")
    return depth == 1 and end <= bounds[1]


def insert_blocks(text: str, blocks: list) -> tuple:
    """(new text, reason); the blocks go in front of the array's closing bracket."""
    bounds, why = array_bounds(text)
    if bounds is None:
        return None, why
    close = bounds[1]
    code = lex(text).code_only
    nl = "\r\n" if "\r\n" in text else "\n"
    body = "".join(blocks).replace("\n", nl)
    prev = close - 1
    while prev >= 0 and code[prev].isspace():
        prev -= 1
    line_start = text.rfind("\n", 0, close) + 1
    own_line = text[line_start:close].strip() == ""
    edits = [(line_start, body) if own_line else (close, nl + body)]
    if code[prev] not in "[,":
        edits.append((prev + 1, ","))
    for at, add in sorted(edits, reverse=True):
        text = text[:at] + add + text[at:]
    return text, ""

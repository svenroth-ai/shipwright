"""Drop here-document bodies from a shell command line before it is parsed (``git_commit_command``).

A heredoc body is data fed to a command's stdin -- a commit message, a file being
written -- so ``cat > notes.md <<'EOF' ... git commit ... EOF`` runs no commit. The
lines after an unquoted ``<<WORD`` / ``<<'WORD'`` / ``<<"WORD"`` / ``<<-WORD`` operator
up to the line that is exactly ``WORD`` (leading tabs stripped for ``<<-``) are
removed; the operator line itself is kept, so ``git commit -F - <<EOF`` is still a
commit. ``<<<`` (a here-string) is not a heredoc.

Never fails open on purpose: an operator inside quotes (``echo "a <<EOF"``) or a
``#`` comment (``echo hi # <<EOF``) starts nothing, and a body line of an UNQUOTED delimiter that holds a command
substitution (``$(`` or a backtick) is kept, because the shell runs it. Pure, stdlib-only.
"""

from __future__ import annotations

import re

_OPERATOR = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(['\"]?)([A-Za-z0-9_][\w.\-]*)\2")


def _live(line: str, pos: int) -> bool:
    """True when *pos* in *line* is outside quotes and before any ``#`` comment."""
    quote = ""
    i = 0
    while i < pos:
        ch = line[i]
        if ch == "\\" and quote != "'":
            i += 2
            continue
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t;&|()"):
            return False  # a comment: nothing after it is shell syntax
        i += 1
    return not quote


def strip_heredoc_bodies(command: str) -> str:
    """*command* without the body lines of its here-documents (delimiter lines dropped too)."""
    kept: list[str] = []
    pending: list[tuple[bool, bool, str]] = []  # (strip tabs, quoted, delimiter)
    for line in command.split("\n"):
        if pending:
            strip_tabs, quoted, word = pending[0]
            bare = line.rstrip("\r")
            if (bare.lstrip("\t") if strip_tabs else bare) == word:
                pending.pop(0)
            elif not quoted and ("$(" in line or "`" in line):
                kept.append(line)  # the shell expands it: keep it visible to the parser
            continue
        kept.append(line)
        pending = [(m.group(1) == "-", bool(m.group(2)), m.group(3))
                   for m in _OPERATOR.finditer(line) if _live(line, m.start())]
    return "\n".join(kept)

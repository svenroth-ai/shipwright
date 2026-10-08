"""Drop here-document bodies from a shell command line before it is parsed (``git_commit_command``).

A heredoc body is data fed to a command's stdin -- a commit message, a file being
written -- so ``cat > notes.md <<'EOF' ... git commit ... EOF`` runs no commit. The
lines after an unquoted ``<<WORD`` / ``<<'WORD'`` / ``<<"WORD"`` / ``<<-WORD`` operator
up to the line that is exactly ``WORD`` (leading tabs stripped for ``<<-``) are
removed; the operator line itself is kept, so ``git commit -F - <<EOF`` is still a
commit. ``<<<`` (a here-string) is not a heredoc, nor is a ``WORD`` that does not
start with a letter or ``_`` (``<<2``), nor ``<<`` inside ``$((...))`` (a shift).

Never fails open on purpose:

* A body fed to a shell or interpreter (``bash`` ``sh`` ``zsh`` ``dash`` ``ksh``
  ``pwsh`` ``powershell`` ``eval`` ``ssh``, or any command given ``-s``, anywhere in
  the operator line's pipeline -- ``bash <<EOF``, ``cat <<EOF | sh``, ``ssh host
  <<EOF``) IS commands: it is kept, so the parser scans it like any other line.
* An operator inside quotes -- including a quote opened on an earlier line
  (``echo "a`` / ``<<EOF"``) -- or after a ``#`` comment starts nothing.
* A body line of an UNQUOTED delimiter that holds a command substitution (``$(`` or
  a backtick) is kept, because the shell runs it.

Pure, stdlib-only.
"""

from __future__ import annotations

import re
from pathlib import Path

_OPERATOR = re.compile(r"<<(?!<)(-?)[ \t]*(['\"]?)([A-Za-z_][\w.\-]*)\2")
_INTERPRETERS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "pwsh", "powershell",
                           "eval", "ssh"})
_WORD = re.compile(r"[^\s;|&()<>'\"]+")


class _State:
    """Lexical state carried from one line to the next: an open quote, ``$((`` depth."""

    def __init__(self) -> None:
        self.quote = ""
        self.arith = 0


def _operators(line: str, state: _State) -> list[re.Match[str]]:
    """The live heredoc operators in *line*, advancing *state* past it."""
    found: list[re.Match[str]] = []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if state.quote == "'":
            state.quote = "" if ch == "'" else state.quote
            i += 1
        elif ch == "\\":
            i += 2
        elif state.quote:
            state.quote = "" if ch == state.quote else state.quote
            i += 1
        elif ch in "'\"":
            state.quote, i = ch, i + 1
        elif ch == "#" and (i == 0 or line[i - 1] in " \t;&|()"):
            break  # a comment: nothing after it is shell syntax
        elif line.startswith("$((", i):
            state.arith, i = state.arith + 1, i + 3
        elif state.arith and line.startswith("))", i):
            state.arith, i = state.arith - 1, i + 2
        elif ch == "<" and not state.arith:
            match = _OPERATOR.match(line, i)
            if match:
                found.append(match)
                i = match.end()
            else:
                while i < n and line[i] == "<":
                    i += 1  # ``<<<`` / ``<<2``: skip the whole run
        else:
            i += 1
    return found


def _program(word: str) -> str:
    name = Path(word).name.lower()
    return name[:-4] if name.endswith((".exe", ".cmd")) else name


def _runs_body(line: str, operator: re.Match[str]) -> bool:
    """True when the pipeline holding *operator* feeds its body to a shell or interpreter."""
    start = max(line.rfind(sep, 0, operator.start()) for sep in ";&") + 1
    ends = [pos for pos in (line.find(sep, operator.end()) for sep in ";&") if pos >= 0]
    words = _WORD.findall(line[start:min(ends, default=len(line))])
    return any(word == "-s" or _program(word) in _INTERPRETERS for word in words)


def strip_heredoc_bodies(command: str) -> str:
    """*command* without the body lines of its data here-documents (delimiter lines too)."""
    kept: list[str] = []
    pending: list[tuple[bool, bool, str, bool]] = []  # (strip tabs, quoted, delimiter, run)
    state = _State()
    for line in command.split("\n"):
        if pending:
            strip_tabs, quoted, word, run = pending[0]
            bare = line.rstrip("\r")
            if (bare.lstrip("\t") if strip_tabs else bare) == word:
                pending.pop(0)
            elif run or (not quoted and ("$(" in line or "`" in line)):
                kept.append(line)  # commands, or expanded by the shell: keep it visible
            continue
        kept.append(line)
        pending = [(m.group(1) == "-", bool(m.group(2)), m.group(3), _runs_body(line, m))
                   for m in _operators(line, state)]
    return "\n".join(kept)

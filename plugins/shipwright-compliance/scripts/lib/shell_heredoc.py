"""Drop here-document bodies from a shell command line before it is parsed (``git_commit_command``).

A heredoc body is data fed to a command's stdin -- a commit message, a file being
written -- so ``cat > notes.md <<'EOF' ... git commit ... EOF`` runs no commit. The
lines after an unquoted ``<<WORD`` / ``<<'WORD'`` / ``<<"WORD"`` / ``<<-WORD`` operator
up to the line that is exactly ``WORD`` (leading tabs stripped for ``<<-``) are
removed; the operator line itself is kept, so ``git commit -F - <<EOF`` is still a
commit. ``<<<`` (a here-string) is not a heredoc, nor is a ``WORD`` that does not
start with a letter or ``_`` (``<<2``), nor ``<<`` inside ``$((...))`` (a shift).

The lexer tracks nesting like the shell does: inside ``"..."`` a ``$(`` (or a
backtick) opens a command substitution where quotes and operators are live again, so
the canonical ``git commit -m "$(cat <<'EOF'`` / message / ``EOF`` / ``)"`` strips the
message -- an odd quote or a ``<<WORD`` inside it is data.

Never fails open on purpose:

* A body fed to a shell or interpreter (``bash`` ``sh`` ``zsh`` ``dash`` ``ksh``
  ``fish`` ``pwsh`` ``powershell`` ``eval`` ``source`` ``ssh``, ``.`` as a command,
  or ``-s`` given to a shell or to ``sudo`` / ``su`` / ``doas``, anywhere in the
  operator line's pipeline -- ``bash <<EOF``, ``cat <<EOF | sh``, ``ssh host
  <<EOF``, ``sudo -s <<EOF``) IS commands: it is kept, so the parser scans it like
  any other line. ``-s`` given to any other program (``git commit -s``: sign-off)
  does not count.
* An operator inside single quotes, or inside double quotes outside any ``$(...)``
  -- including a quote opened on an earlier line (``echo "a`` / ``<<EOF"``) -- or
  after a ``#`` comment starts nothing.
* A body line of an UNQUOTED delimiter that holds a command substitution (``$(`` or
  a backtick) is kept, because the shell runs it.

Pure, stdlib-only.
"""

from __future__ import annotations

import re
from pathlib import Path

_OPERATOR = re.compile(r"<<(?!<)(-?)[ \t]*(['\"]?)([A-Za-z_][\w.\-]*)\2")
_INTERPRETERS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "fish", "pwsh",
                           "powershell", "eval", "source", "ssh"})
_DASH_S_SHELLS = _INTERPRETERS | {"sudo", "su", "doas"}  # where ``-s`` reads a shell
_WORD = re.compile(r"[^\s;|&()<>'\"]+")
_ARITH = ("((", "a(")  # ``$((`` and a plain paren inside it


class _State:
    """Lexical state carried from one line to the next: the open contexts, innermost last.

    ``'`` / ``"`` an open quote, ``(`` a command substitution or subshell, a backtick
    a backtick substitution, ``((`` an arithmetic expansion, ``a(`` a paren inside one.
    """

    def __init__(self) -> None:
        self.stack: list[str] = []

    @property
    def top(self) -> str:
        return self.stack[-1] if self.stack else ""


def _step(line: str, i: int, state: _State) -> int:
    """Advance past one non-operator token at *i* in a command context; the new index."""
    ch, top = line[i], state.top
    if ch == "\\":
        return i + 2
    if ch in "'\"":
        state.stack.append(ch)
    elif ch == "`":
        if top == "`":
            state.stack.pop()
        else:
            state.stack.append("`")
    elif line.startswith("$((", i):
        state.stack.append("((")
        return i + 3
    elif line.startswith("$(", i) or ch == "(":
        state.stack.append("(")
        return i + (2 if ch == "$" else 1)
    elif ch == ")" and top == "(":
        state.stack.pop()
    return i + 1


def _arith_step(line: str, i: int, state: _State) -> int:
    if state.top == "((" and line.startswith("))", i):
        state.stack.pop()
        return i + 2
    if line[i] == "(":
        state.stack.append("a(")
    elif line[i] == ")" and state.top == "a(":
        state.stack.pop()
    return i + 1


def _operators(line: str, state: _State) -> list[re.Match[str]]:
    """The live heredoc operators in *line*, advancing *state* past it."""
    found: list[re.Match[str]] = []
    i, n = 0, len(line)
    while i < n:
        ch, top = line[i], state.top
        if top == "'":
            if ch == "'":
                state.stack.pop()
            i += 1
        elif top == '"':
            if ch == '"':
                state.stack.pop()
            if ch == "\\":
                i += 2
            elif ch == "`" or line.startswith("$(", i):
                i = _step(line, i, state)  # a substitution: live syntax again
            else:
                i += 1
        elif top in _ARITH:
            i = _arith_step(line, i, state)
        elif ch == "#" and (i == 0 or line[i - 1] in " \t;&|()"):
            break  # a comment: nothing after it on this line is shell syntax
        elif ch == "<":
            match = _OPERATOR.match(line, i)
            if match:
                found.append(match)
                i = match.end()
            else:
                while i < n and line[i] == "<":
                    i += 1  # ``<<<`` / ``<<2``: skip the whole run
        else:
            i = _step(line, i, state)
    return found


def _program(word: str) -> str:
    name = Path(word).name.lower()
    return name[:-4] if name.endswith((".exe", ".cmd")) else name


def _feeds_shell(words: list[str]) -> bool:
    """True when one pipeline stage (*words*) reads its stdin as commands."""
    if words and words[0] == ".":
        return True  # ``. /dev/stdin``: the POSIX ``source``
    programs = [_program(word) for word in words]
    if any(program in _INTERPRETERS for program in programs):
        return True
    return "-s" in words and any(
        program in _DASH_S_SHELLS for program in programs[:words.index("-s")])


def _runs_body(line: str, operator: re.Match[str]) -> bool:
    """True when the pipeline holding *operator* feeds its body to a shell or interpreter."""
    start = max(line.rfind(sep, 0, operator.start()) for sep in ";&") + 1
    ends = [pos for pos in (line.find(sep, operator.end()) for sep in ";&") if pos >= 0]
    pipeline = line[start:min(ends, default=len(line))]
    return any(_feeds_shell(_WORD.findall(stage)) for stage in pipeline.split("|"))


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

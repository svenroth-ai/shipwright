"""Is a shell command line a real ``git ... commit`` invocation? (``check_rtm_coverage``).

Pure, stdlib-only: the hook fires on every Bash call and must not misfire on text
that merely mentions "git commit" (``rg "git commit"``, ``git log --grep``), nor
fail open for the wrappers people actually type (``env``, ``sudo``, ``timeout 60``,
``sh -c '...'``, ``eval``, ``pwsh -Command``, ``cmd /c``), shell compound syntax
(``if ...; then git commit; fi``, ``{ ...; }``, ``! ...``), a ``#`` inside a word
(``curl http://h/#a && git commit``) or a backslash-continued line.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

# git global options that consume the following token (``git -C <path> commit``).
_GIT_OPTS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
_SEPARATOR_CHARS = frozenset(";|&()")
_ENV_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# Closed set of wrappers that run their argument as a command, with the options of
# each that consume the next token (``nice -n 5 git commit``, ``sudo -u x git commit``).
_WRAPPERS: dict[str, frozenset[str]] = {
    "env": frozenset({"-u", "--unset", "-C", "--chdir", "-S"}),
    "command": frozenset(), "exec": frozenset({"-a"}), "time": frozenset({"-f", "-o"}),
    "nice": frozenset({"-n", "--adjustment"}), "nohup": frozenset(),
    "sudo": frozenset({"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"}),
    "xargs": frozenset({"-a", "-d", "-E", "-I", "-L", "-n", "-P", "-s"}),
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
}
_SHELLS = frozenset({"sh", "bash", "zsh", "dash"})
_POWERSHELLS = frozenset({"pwsh", "powershell"})
# Closed set of shell reserved words that may precede a command in a segment.
_RESERVED = frozenset({"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}"})
_MAX_SHELL_DEPTH = 3


def _program(token: str) -> str:
    name = Path(token).name.lower()
    return name[:-4] if name.endswith(".exe") else name


def _skip_wrappers(tokens: list[str]) -> int:
    """Index of the real program after reserved words, ``VAR=val`` and wrappers (+ args)."""
    i = 0
    while i < len(tokens):
        if tokens[i] in _RESERVED or _ENV_ASSIGNMENT.match(tokens[i]):
            i += 1  # then git commit / ! git commit / FOO=bar git commit
            continue
        name = _program(tokens[i])
        if name not in _WRAPPERS:
            return i
        i += 1
        while i < len(tokens) and tokens[i].startswith("-"):
            i += 2 if tokens[i] in _WRAPPERS[name] else 1
        if name == "timeout" and i < len(tokens):
            i += 1  # the duration: timeout 60 git commit
    return i


def _shell_command(tokens: list[str]) -> str | None:
    """The ``-c`` string of ``sh|bash|zsh|dash [-l] -c '<cmd>'`` (``-lc`` too), else None."""
    i, has_c = 1, False
    while i < len(tokens) and tokens[i][:1] in ("-", "+") and tokens[i] != "--":
        if tokens[i] in ("-o", "+o"):
            i += 1  # -o pipefail
        elif not tokens[i].startswith("--") and "c" in tokens[i][1:]:
            has_c = True
        i += 1
    return tokens[i] if has_c and i < len(tokens) else None


def _after_flag(tokens: list[str], is_flag) -> str | None:
    """The rest of the line after the first token matching *is_flag*, joined; else None."""
    for j, token in enumerate(tokens[1:], start=1):
        if is_flag(token.lower()):
            return " ".join(tokens[j + 1:]) or None
    return None


def _inner_command(tokens: list[str]) -> str | None:
    """The command string a shell-like program runs, or None when it is not one.

    ``sh|bash|zsh|dash -c '<cmd>'``, ``eval <words>``, ``pwsh|powershell [...]
    -Command <cmd>`` (any ``-c``/``-Command`` prefix) and ``cmd [/d /q ...] /c|/k <cmd>``.
    """
    name = _program(tokens[0])
    if name in _SHELLS:
        return _shell_command(tokens)
    if name == "eval":
        return " ".join(tokens[1:]) or None
    if name in _POWERSHELLS:
        return _after_flag(tokens, lambda t: len(t) >= 2 and "-command".startswith(t))
    if name == "cmd":
        return _after_flag(tokens, lambda t: t in ("/c", "/k", "//c", "//k"))
    return None


def _segment_is_commit(tokens: list[str], depth: int = 0) -> bool:
    tokens = tokens[_skip_wrappers(tokens):]
    if not tokens or tokens[0].startswith("#"):
        return False  # empty, or a comment: # git commit
    if _program(tokens[0]) in (*_SHELLS, *_POWERSHELLS, "eval", "cmd"):
        inner = _inner_command(tokens)
        return inner is not None and depth < _MAX_SHELL_DEPTH and is_git_commit(inner, depth + 1)
    if _program(tokens[0]) != "git":
        return False
    i = 1
    while i < len(tokens) and tokens[i].startswith("-"):
        i += 2 if tokens[i] in _GIT_OPTS_WITH_VALUE else 1
    return i < len(tokens) and tokens[i] == "commit"


def is_git_commit(command: str, _depth: int = 0) -> bool:
    """True when some ``&&`` / ``;`` / ``|``-separated segment runs ``git ... commit``.

    Global options before the subcommand (``-C <path>``, ``-c k=v``, ``--no-pager``)
    are skipped, as are leading reserved words (``if then else elif do while until
    ! { }``), ``VAR=val`` prefixes and a closed set of wrappers (``env``, ``sudo``,
    ``timeout 60``, ``nohup``, ...); ``sh|bash -c``, ``eval``, ``pwsh -Command`` and
    ``cmd /c`` strings are parsed recursively (depth-capped). ``git -c k=v diff``,
    ``rg "git commit"``, ``echo git commit``, ``# git commit`` and ``git log --grep
    'git commit'`` are not commits. ``#`` is not a comment character to the lexer
    (``http://h/#a`` stays one word; a line comment ends at its newline, which is a
    separator); a segment starting with ``#`` is a comment. Backslash-newline
    continuations are joined first. Unparseable shell text (an unbalanced quote)
    falls back to the substring test so the gate still fires.
    """
    text = command.replace("\\\r\n", " ").replace("\\\n", " ")
    try:
        lexer = shlex.shlex(text.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""  # a '#' must not swallow the rest of the flattened line
        tokens = list(lexer)
    except ValueError:
        return "git commit" in command
    segment: list[str] = []
    for token in [*tokens, ";"]:
        if token and set(token) <= _SEPARATOR_CHARS:
            if _segment_is_commit(segment, _depth):
                return True
            segment = []
        else:
            segment.append(token)
    return False

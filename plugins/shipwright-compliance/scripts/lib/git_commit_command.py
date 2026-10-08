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

from shell_heredoc import strip_heredoc_bodies
from shell_substitution import substitutions

# git global options that consume the following token (``git -C <path> commit``).
_GIT_OPTS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
_SEPARATOR_CHARS = frozenset(";|&()")
_ENV_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# Closed set of wrappers that run their argument as a command, with the options of
# each that consume the next token (``nice -n 5 git commit``, ``sudo -u x git commit``).
_WRAPPERS: dict[str, frozenset[str]] = {
    "env": frozenset({"-u", "--unset", "-C", "--chdir"}),
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
# the unparseable-text fallback: ``git`` then ``commit`` on one logical line
_LOOSE_COMMIT = re.compile(r"\bgit(?:\.exe|\.cmd)?\b[^\n;&|]*\bcommit\b")
# the same, with git's global options captured so the target repo survives (-C, --git-dir, ...)
_LOOSE_OPTS = re.compile(
    r"\bgit(?:\.exe|\.cmd)?\b((?>[ \t]+(?:-[Cc][ \t]+(?:\"[^\"\n]*\"|'[^'\n]*'|\S+)"
    r"|--(?:git-dir|work-tree|namespace)(?:=|[ \t]+)(?:\"[^\"\n]*\"|'[^'\n]*'|\S+)"
    r"|-{1,2}[A-Za-z][\w-]*))*)[ \t]+commit\b")
# env's -S / --split-string: ONE string env splits into argv (``-S<str>``, ``-iS <str>`` too).
_ENV_SPLIT_SHORT = re.compile(r"-[i0v]*S(.*)", re.DOTALL)


def _loose_commits(text: str):
    """Per line, a regex reading of ``git [global options] commit`` for text shlex rejects.

    Keeps ``-C`` / ``--git-dir`` / ``--work-tree`` so the commit is still judged on its repo;
    a line that mentions git and commit in some other shape yields ``()`` (over-fires).
    """
    for line in text.split("\n"):
        matched = 0
        for found in _LOOSE_OPTS.finditer(line):
            matched += 1
            try:
                yield tuple(shlex.split(found.group(1)))
            except ValueError:
                yield tuple(word.strip("'\"") for word in found.group(1).split())
        for _ in range(len(_LOOSE_COMMIT.findall(line)) - matched):
            yield ()  # a commit only the looser pattern saw: judged on the default repo


def _program(token: str) -> str:
    name = Path(token).name.lower()
    return name[:-4] if name.endswith((".exe", ".cmd")) else name  # git.exe, git.cmd


def _env_split_string(tokens: list[str], i: int) -> tuple[str | None, int]:
    """``(string, tokens consumed)`` when ``tokens[i]`` is env's split-string option, else ``(None, 0)``."""
    token = tokens[i]
    if token.startswith("--split-string="):
        return token[len("--split-string="):], 1
    attached = _ENV_SPLIT_SHORT.fullmatch(token)
    if token == "--split-string" or attached:
        if attached and attached.group(1):
            return attached.group(1), 1
        return (tokens[i + 1], 2) if i + 1 < len(tokens) else (None, 0)
    return None, 0


def _skip_wrappers(tokens: list[str]) -> tuple[int, str | None]:
    """Index of the real program after reserved words, ``VAR=val`` and wrappers (+ args).

    The second value is the string of ``env -S <string>``: the index then points
    past it, at the arguments env appends to the split argv.
    """
    i = 0
    while i < len(tokens):
        if tokens[i] in _RESERVED or _ENV_ASSIGNMENT.match(tokens[i]):
            i += 1  # then git commit / ! git commit / FOO=bar git commit
            continue
        name = _program(tokens[i])
        if name not in _WRAPPERS:
            return i, None
        i += 1
        while i < len(tokens) and tokens[i].startswith("-"):
            if name == "env":
                split, used = _env_split_string(tokens, i)
                if split is not None:
                    return i + used, split
            i += 2 if tokens[i] in _WRAPPERS[name] else 1
        if name == "timeout" and i < len(tokens):
            i += 1  # the duration: timeout 60 git commit
    return i, None


def _env_split_commits(split: str, rest: list[str], depth: int):
    """``env -S '<split>' <rest>`` runs ``env <split words> <rest>``: parse that, depth-bounded."""
    if depth >= _MAX_SHELL_DEPTH:
        if _LOOSE_COMMIT.search(" ".join([split, *rest])):  # too deep: over-fire, never fail open
            yield ()
        return
    try:
        words = shlex.split(split)
    except ValueError:
        if _LOOSE_COMMIT.search(split):
            yield ()
        return
    yield from _segment_commits(["env", *words, *rest], depth + 1)


def _shell_command(tokens: list[str]) -> str | None:
    """The ``-c`` string of ``sh|bash|zsh|dash [-l] -c '<cmd>'`` (``-lc`` too), else None."""
    i, has_c = 1, False
    while i < len(tokens) and tokens[i][:1] in ("-", "+") and tokens[i] != "--":
        if tokens[i] in ("-o", "+o"):
            i += 1  # -o pipefail
        elif not tokens[i].startswith("--") and "c" in tokens[i][1:]:
            has_c = True
        i += 1
    if has_c and i < len(tokens) and tokens[i] == "--":
        i += 1  # ``bash -c -- 'cmd'``
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


def _segment_commits(tokens: list[str], depth: int = 0):
    """git's global options for EACH ``git ... commit`` the segment runs (``()`` unparsed).

    One for a plain ``git ... commit``; every inner commit of a ``sh -c`` / ``eval`` /
    ``pwsh -Command`` / ``cmd /c`` string; one for an ``env -S`` string.
    """
    start, split = _skip_wrappers(tokens)
    if split is not None:
        yield from _env_split_commits(split, tokens[start:], depth)
        return
    tokens = tokens[start:]
    if not tokens or tokens[0].startswith("#"):
        return  # empty, or a comment: # git commit
    if _program(tokens[0]) in (*_SHELLS, *_POWERSHELLS, "eval", "cmd"):
        inner = _inner_command(tokens)
        if inner is None:
            return
        if depth >= _MAX_SHELL_DEPTH:  # too deep to parse: over-fire, never fail open
            if _LOOSE_COMMIT.search(inner):
                yield ()
            return
        yield from iter_git_commits(inner, depth + 1)
        return
    if _program(tokens[0]) != "git":
        return
    i = 1
    while i < len(tokens) and tokens[i].startswith("-"):
        i += 2 if tokens[i] in _GIT_OPTS_WITH_VALUE else 1
    if i < len(tokens) and tokens[i] == "commit":
        yield tuple(tokens[1:i])


def is_git_commit(command: str, _depth: int = 0) -> bool:
    """True when some segment (split on ``&&`` ``||`` ``;`` ``|`` ``&`` ``(`` ``)``) runs ``git ... commit``.

    Global options before the subcommand (``-C <path>``, ``-c k=v``, ``--no-pager``)
    are skipped, as are leading reserved words (``if then else elif do while until
    ! { }``), ``VAR=val`` prefixes and a closed set of wrappers (``env``, ``sudo``,
    ``timeout 60``, ``nohup``, ...); ``sh|bash -c``, ``eval``, ``pwsh -Command`` and
    ``cmd /c`` strings, command substitutions (``$(...)``, backticks) and ``env -S`` /
    ``--split-string`` strings (split into env's argv, so their words are one segment)
    are parsed recursively, every inner commit counting; past the depth cap the substring test
    decides (over-fires rather than fails open). ``git -c k=v diff``,
    ``rg "git commit"``, ``echo git commit``, ``# git commit`` and ``git log --grep
    'git commit'`` are not commits. ``#`` is not a comment character to the lexer
    (``http://h/#a`` stays one word; a line comment ends at its newline, which is a
    separator); a segment starting with ``#`` is a comment. Backslash-newline
    continuations are joined first. Unparseable shell text (an unbalanced quote)
    falls back to the substring test so the gate still fires. Known over-fires: a
    trailing comment holding a separator (``echo hi # ; git commit``), a quoted
    separator that ``eval`` / ``-Command`` / ``cmd /c`` re-join without its quotes
    (``eval echo "a; git commit"``), and ``git commit --dry-run`` / ``-h``. Here-document
    bodies are data, not commands (``shell_heredoc``). ``git.exe`` / ``git.cmd`` and
    ``command git`` are git; a user-configured git alias (``git ci``) is NOT covered.
    """
    return find_git_commit(command, _depth) is not None


def find_git_commit(command: str, _depth: int = 0) -> tuple[str, ...] | None:
    """The global options of the first ``git ... commit`` in *command* (:func:`is_git_commit`).

    ``()`` when it has none, or when only the substring fallback found the commit
    (unparseable text, past the depth cap); ``None`` when *command* runs no commit.
    """
    return next(iter_git_commits(command, _depth), None)


def iter_git_commits(command: str, _depth: int = 0):
    """The global options of every ``git ... commit`` in *command*, in order.

    Top-level segments first, then those inside command substitutions (``$(...)``,
    backticks, ``<(...)``: :mod:`shell_substitution`), each parsed as a command line.
    A commit written both ways in one line may be yielded twice.
    """
    text = strip_heredoc_bodies(command)
    flat = text  # continuations are already joined outside bodies (shell_heredoc)
    try:
        lexer = shlex.shlex(flat.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""  # a '#' must not swallow the rest of the flattened line
        tokens = list(lexer)
    except ValueError:  # unparseable (a stray quote): over-fire on any git ... commit
        yield from _loose_commits(text)
        return
    segment: list[str] = []
    for token in [*tokens, ";"]:
        if token and set(token) <= _SEPARATOR_CHARS:
            yield from _segment_commits(segment, _depth)
            segment = []
        else:
            segment.append(token)
    try:
        inners = substitutions(flat)
    except RecursionError:  # absurdly nested: over-fire, never fail open
        inners = [flat] if _LOOSE_COMMIT.search(flat) else []
        _depth = _MAX_SHELL_DEPTH
    for inner in inners:
        if _depth >= _MAX_SHELL_DEPTH:  # too deep to parse: over-fire, never fail open
            if _LOOSE_COMMIT.search(inner):
                yield ()
        else:
            yield from iter_git_commits(inner, _depth + 1)

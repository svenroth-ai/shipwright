#!/usr/bin/env python3
"""Shell-command policy for ``iterate_worktree_gate.py`` (Claude Code side).

Answers one question for a ``Bash``/``PowerShell`` call made while an iterate
session is armed but not yet isolated: *is this command safe to run before the
worktree exists?* Safe = the mandated setup call itself, or a read-only /
housekeeping command the skill's own pre-setup steps need (banner, project
validation, the B1 resume menu, abandoning a stale worktree). Everything else
is blocked, because a shell that can write can also leak into the main tree.

Tokenizing reuses ``codex_pretooluse_matcher``'s helpers, so the two gates
agree on what a "single semantically active command" looks like (``|``, ``||``,
``&``, redirection, ``$(...)``, backticks and newlines are never allowed).
Unlike the Codex gate -- one shot, first call only -- this policy is evaluated
on EVERY shell call until isolation exists, so it is deliberately an allowlist.
Cooperative enforcement, not an adversarial boundary: the goal is a model that
forgot the setup step, not one trying to smuggle a write past the hook."""

from __future__ import annotations

import re
import shlex
import sys

from codex_pretooluse_matcher import (
    _REDIRECTION_OR_GROUPING,
    _UNSAFE_SUBSTRINGS,
    _basename,
    _segment_targets_setup,
    _segments,
    _unquote,
    has_unsafe_punctuation,
    segment_script_basename,
)

#: Programs with no write capability once redirection is rejected. Compared
#: case-insensitively so the PowerShell cmdlet spellings match too.
_READ_ONLY_PROGRAMS = frozenset({
    "cd", "pwd", "ls", "dir", "echo", "cat", "head", "tail", "wc", "which",
    "where", "type", "true", "test",
    "set-location", "get-location", "get-childitem", "get-content", "test-path",
})
#: ``git`` subcommands that only read local state (no ``fetch``/``ls-remote``: they contact a remote;
#: setup_iterate_worktree.py does its own fetch).
_GIT_READ_SUBCOMMANDS = frozenset({
    "status", "log", "diff", "show", "rev-parse", "rev-list", "merge-base",
    "describe", "ls-files", "for-each-ref",
})
#: Subcommands allowed only in the forms the skill's pre-setup steps need.
#: B1 "Abandon" removes a stale worktree/branch before a fresh setup, so
#: ``worktree`` and ``branch`` appear -- but never in a creating form.
_GIT_WORKTREE_ACTIONS = frozenset({"list", "remove", "prune"})
_GIT_BRANCH_FLAGS = frozenset({
    "-d", "-D", "--delete", "--list", "--show-current", "-a", "-r", "-v", "-vv",
    "--merged", "--no-merged",
})
_GIT_REMOTE_ACTIONS = frozenset({"-v", "get-url"})
_GIT_VALUE_FLAGS = ("-C", "-c", "--git-dir", "--work-tree")
#: Skill scripts that read project state only (B1 resume menu, health, scoring).
_SAFE_SCRIPTS = frozenset({
    "list_iterate_branches.py", "main_health.py",
    "classify_complexity.py", "classify_intent.py",
})


def _tokenize(command: object) -> list[list[str]] | None:
    """Segments of ``command`` split on ``&&``/``;``, or ``None`` when the
    command has any shape that cannot be judged segment-by-segment."""
    if not isinstance(command, str) or not command.strip():
        return None
    # SKILL.md prints the setup call with a trailing-backslash line continuation.
    command = command.strip().replace("\\\r\n", " ").replace("\\\n", " ")
    if any(marker in command for marker in _UNSAFE_SUBSTRINGS):
        return None
    try:
        lexer = shlex.shlex(command, posix=(sys.platform != "win32"), punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""  # bash keeps a mid-word '#'; shlex would drop the rest of the command
        tokens = [_unquote(t) for t in lexer]
    except ValueError:
        return None
    if "||" in tokens or "|" in tokens or "&" in tokens:
        return None
    if any(t in _REDIRECTION_OR_GROUPING for t in tokens) or has_unsafe_punctuation(tokens):
        return None
    return _segments(tokens) or None


def _git_args(segment: list[str]) -> list[str]:
    """Tokens after ``git`` and its own global flags: ``[subcommand, *args]``."""
    idx = 1
    while idx < len(segment) and segment[idx].startswith("-"):
        flag = segment[idx]
        idx += 1
        if flag in _GIT_VALUE_FLAGS and idx < len(segment):
            idx += 1
    return segment[idx:]


def _is_iterate_worktree_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    return ".." not in parts and ".worktrees" in parts[:-1]


def _git_is_safe(segment: list[str]) -> bool:
    # ``-c k=v`` / ``--config-env`` / ``--exec-path`` make git run a configured command
    # (``-c diff.external=...``); none of the pre-setup steps need them.
    if any(f.startswith(("-c", "--config-env", "--exec-path")) and f != "-C" for f in segment[1 : len(segment) - len(_git_args(segment))]):
        return False
    sub, *args = _git_args(segment) or [""]
    if sub in _GIT_READ_SUBCOMMANDS:
        # ``--output=<file>`` writes a file; the others run a configured command.
        return not any(a.startswith(("--output", "--upload-pack", "--receive-pack", "--ext-diff", "--textconv")) for a in args)
    if sub == "worktree":
        if not args or args[0] not in _GIT_WORKTREE_ACTIONS:
            return False
        # B1 Abandon removes an iterate worktree; never an arbitrary one.
        targets = [a for a in args[1:] if not a.startswith("-")]
        return args[0] != "remove" or (bool(targets) and all(_is_iterate_worktree_path(t) for t in targets))
    if sub == "branch":
        flags = [a for a in args if a.startswith("-")]
        if not args:
            return True
        if not flags or not all(f in _GIT_BRANCH_FLAGS for f in flags):
            return False
        # A bare name creates a branch (``-v name`` still does); only delete/--list take one.
        names = [a for a in args if not a.startswith("-")]
        if any(f in {"-d", "-D", "--delete"} for f in flags):  # B1 Abandon deletes iterate/<slug> only
            return bool(names) and all(n.startswith("iterate/") for n in names)
        return not names or "--list" in flags
    if sub == "remote":
        return not args or args[0] in _GIT_REMOTE_ACTIONS
    return False


#: ``SHIPWRIGHT_*=value`` prefix (POSIX) or a lone ``$env:SHIPWRIGHT_*=value``
#: segment (PowerShell) -- the documented offline recovery is
#: ``SHIPWRIGHT_ITERATE_NO_FETCH=1 uv run ... setup_iterate_worktree.py``.
_ENV_PREFIX = re.compile(r"^(?:\$env:)?SHIPWRIGHT_[A-Z0-9_]+=\S*$", re.IGNORECASE)


def _segment_is_safe(segment: list[str]) -> bool:
    while segment and _ENV_PREFIX.match(segment[0]):
        segment = segment[1:]
    if not segment:  # a bare ``$env:SHIPWRIGHT_X=1`` segment: sets nothing but the shell's env
        return True
    if _segment_targets_setup(segment):
        return True
    program = _basename(segment[0]).lower()
    if program in _READ_ONLY_PROGRAMS:
        return True
    if program == "git":
        return _git_is_safe(segment)
    script = segment_script_basename(segment)
    if script == "record_review_pass.py":  # B1 resume replay-check: read-only `show` only
        idx = next(i for i, t in enumerate(segment) if _basename(t) == script)
        return segment[idx + 1 : idx + 2] == ["show"] and "record" not in segment
    return script in _SAFE_SCRIPTS


def shell_is_preflight_safe(tool_input: object) -> bool:
    """True iff every segment of the call's ``command`` is allowlisted."""
    if not isinstance(tool_input, dict):
        return False
    segments = _tokenize(tool_input.get("command"))
    return segments is not None and all(_segment_is_safe(s) for s in segments)

"""Which repository a ``git ... commit`` command commits to (``check_rtm_coverage``).

The commit gate must measure the repo the commit lands in, not the directory the
hook happens to run in: ``git -C ../other commit`` commits to ``../other``. git
applies its global options in order -- each ``-C <path>`` changes directory
(relative to the previous one; an empty path is a no-op), and a relative
``--git-dir`` / ``--work-tree`` is resolved against the directory reached. With
``--work-tree`` that tree is the project; with only ``--git-dir`` git treats the
directory reached as the top of the work tree, so that directory is the project
and the git dir must be handed to every git read (``GIT_DIR``). A plain ``-C``
may name a subdirectory (``git -C repo/src commit`` commits to ``repo``): the
project is the nearest directory at or above it holding ``.shipwright/`` or a
``shipwright_*_config.json``, never above the repo root (the first ``.git``); with
neither, the directory reached.

Not covered: ``cd <path> && git commit`` and ``env -C <path> git commit`` (the
command's own directory changes), a ``GIT_DIR`` / ``GIT_WORK_TREE`` set in the
command text, and a commit found only by a fallback (``env -S``, past the shell
depth cap), which carries no options. Pure apart from ``stat`` calls.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import NamedTuple

from git_commit_command import iter_git_commits

_MSYS_DRIVE = re.compile(r"^/([A-Za-z])(?=/|$)")


class CommitTarget(NamedTuple):
    project_root: Path
    git_dir: Path | None
    work_tree: Path | None


def _native(value: str) -> str:
    """``~`` expanded; on Windows an MSYS ``/c/x`` path is ``c:/x`` (what Git Bash means)."""
    value = os.path.expanduser(value)
    if os.name == "nt":
        value = _MSYS_DRIVE.sub(lambda m: f"{m.group(1)}:", value)
    return value


def _options(opts: tuple[str, ...]) -> list[tuple[str, str]]:
    """``(name, value)`` for each ``-C`` / ``--git-dir`` / ``--work-tree`` in order."""
    found: list[tuple[str, str]] = []
    i = 0
    while i < len(opts):
        name, eq, value = opts[i].partition("=")
        if eq and name in ("--git-dir", "--work-tree"):
            found.append((name, value))
            i += 1
        elif opts[i] in ("-C", "--git-dir", "--work-tree") and i + 1 < len(opts):
            found.append((opts[i], opts[i + 1]))
            i += 2
        else:
            i += 2 if opts[i] in ("-c", "--namespace") else 1
    return found


def _is_project(directory: Path) -> bool:
    return (directory / ".shipwright").is_dir() or any(directory.glob("shipwright_*_config.json"))


def _project_dir(start: Path) -> Path:
    """The project between *start* and its repo root (the first ``.git`` above), else
    that root; *start* itself when no repo encloses it."""
    chain = [start, *start.parents]
    try:
        top = next((i for i, d in enumerate(chain) if (d / ".git").exists()), None)
        if top is None:
            return start
        return next((d for d in chain[:top + 1] if _is_project(d)), chain[top])
    except OSError:
        return start


def _locate(opts: tuple[str, ...], cwd: str | Path) -> CommitTarget | None:
    located = _options(opts)
    if not located:
        return None
    base = Path(cwd)
    git_dir = work_tree = None
    for name, value in located:
        if name == "-C":
            base = base / _native(value) if value else base
        elif name == "--git-dir":
            git_dir = value
        else:
            work_tree = value
    base = Path(os.path.normpath(base))
    tree = _under(base, work_tree) if work_tree else None
    if tree is None and git_dir is None and base.is_dir():
        base = _project_dir(base)
    return CommitTarget(tree or base, _under(base, git_dir) if git_dir else None, tree)


def commit_targets(command: str, cwd: str | Path) -> list[CommitTarget | None]:
    """One entry per commit in *command*, in order; ``None`` for a commit naming no location."""
    return [_locate(opts, cwd) for opts in iter_git_commits(command)]


def commit_target(command: str, cwd: str | Path) -> CommitTarget | None:
    """Where the first commit in *command* lands, or ``None`` (no commit, or no location)."""
    targets = commit_targets(command, cwd)
    return targets[0] if targets else None


def _under(base: Path, value: str) -> Path:
    return Path(os.path.normpath(base / _native(value)))

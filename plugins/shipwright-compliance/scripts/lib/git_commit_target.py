"""Which repository a ``git ... commit`` command commits to (``check_rtm_coverage``).

The commit gate must measure the repo the commit lands in, not the directory the
hook happens to run in: ``git -C ../other commit`` commits to ``../other``. git
applies its global options in order -- each ``-C <path>`` changes directory
(relative to the previous one; an empty path is a no-op), and a relative
``--git-dir`` / ``--work-tree`` is resolved against the directory reached. With
``--work-tree`` that tree is the project (the commit still lands in the repo
found from the directory reached, so its git dir is looked up there --
``rtm_commit_scope``) and the project is resolved from it exactly as from a plain
``-C`` below (a monorepo work tree with the project in a subdirectory descends into
it; none found is :attr:`CommitTarget.found` False); with only ``--git-dir`` git treats the directory reached as
the top of the work tree, so that directory is the project and the git dir must be
handed to every git read (``GIT_DIR``). A plain ``-C`` names a directory the
project is resolved from by the SHARED resolver (``shared/scripts/lib/project_root``
steps 2-4, the reached directory as cwd, ``SHIPWRIGHT_PROJECT_ROOT`` not consulted
for a named location): the directory itself, its single project subdirectory
(``git -C <repo root> commit`` with the project in ``webui/``), or the nearest
project above it, never above the repo root. A stray ``.shipwright/`` holding no
``.shipwright/agent_docs`` and no config marker is no project. When nothing resolves,
:attr:`CommitTarget.found` is False and the directory reached is measured.

Not covered: ``cd <path> && git commit`` and ``env -C <path> git commit`` (the
command's own directory changes), a ``GIT_DIR`` / ``GIT_WORK_TREE`` set in the
command text, and a commit found only by a fallback (``env -S``, past the shell
depth cap), which carries no options. Pure apart from ``stat`` / ``iterdir`` calls.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

from git_commit_command import iter_git_commits

_MSYS_DRIVE = re.compile(r"^/([A-Za-z])(?=/|$)")


_SHARED_PROJECT_ROOT = (Path(__file__).resolve().parents[4] / "shared" / "scripts" / "lib"
                        / "project_root.py")
_RESOLVER_MODULE = "_shipwright_shared_project_root"  # a sentinel name: never ``lib.*`` (ADR-045)


class CommitTarget(NamedTuple):
    project_root: Path
    git_dir: Path | None
    work_tree: Path | None
    base: Path  # the directory git reached (``-C`` applied): where the repo is found
    found: bool = True  # False: no Shipwright project resolved from a plain ``-C``
    note: str | None = None  # why the resolution is uncertain (WARN text)


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


def _resolver():
    """The shared ``project_root`` module, loaded by file under a sentinel name.

    The hook loads ``lib.project_root`` after a ``sys.path`` insert; in-process
    (tests) ``lib`` may already be this plugin's own package, so a by-name import
    would be inert. Registered in ``sys.modules`` before it executes.
    """
    module = sys.modules.get(_RESOLVER_MODULE)
    if module is None:
        spec = importlib.util.spec_from_file_location(_RESOLVER_MODULE, _SHARED_PROJECT_ROOT)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {_SHARED_PROJECT_ROOT}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_RESOLVER_MODULE] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(_RESOLVER_MODULE, None)
            raise
    return module


def _project_dir(start: Path) -> tuple[Path, bool, str | None]:
    """``(project, found, note)`` resolved from *start* (shared resolver, no env override)."""
    try:
        shared = _resolver()
    except Exception as exc:  # noqa: BLE001 - the gate must WARN, never crash
        return start, False, (f"the shared project resolver could not be loaded "
                              f"({type(exc).__name__}); measured {start}")
    try:
        root = shared.resolve_project_root(allow_env=False, cwd=start)
    except (ValueError, OSError) as exc:
        return start, False, f"{str(exc)[:200]} -- measured {start}"
    return root, shared.is_shipwright_project(root), None


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
    gdir = _under(base, git_dir) if git_dir else None
    if tree is not None and tree.is_dir():  # the work tree is resolved like a ``-C``
        root, found, note = _project_dir(tree)
        return CommitTarget(root, gdir, tree, base, found, note)
    if tree is None and gdir is None and base.is_dir():
        root, found, note = _project_dir(base)
        return CommitTarget(root, None, None, base, found, note)
    return CommitTarget(tree or base, gdir, tree, base)


def commit_targets(command: str, cwd: str | Path) -> list[CommitTarget | None]:
    """One entry per commit in *command*, in order; ``None`` for a commit naming no location."""
    return [_locate(opts, cwd) for opts in iter_git_commits(command)]


def commit_target(command: str, cwd: str | Path) -> CommitTarget | None:
    """Where the first commit in *command* lands, or ``None`` (no commit, or no location)."""
    targets = commit_targets(command, cwd)
    return targets[0] if targets else None


def _under(base: Path, value: str) -> Path:
    return Path(os.path.normpath(base / _native(value)))

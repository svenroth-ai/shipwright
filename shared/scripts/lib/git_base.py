"""Low-level git subprocess primitives (dependency-free leaf module).

Extracted from :mod:`worktree_isolation` so :mod:`repo_root` can use
``GitError`` / ``main_repo_root`` WITHOUT importing ``worktree_isolation`` —
that closed the ``worktree_isolation -> events_log -> repo_root ->
worktree_isolation`` import cycle (CodeQL ``py/cyclic-import``). This module
imports only the stdlib, so both ``worktree_isolation`` (which re-exports these
names for its existing callers) and ``repo_root`` depend on it without forming a
cycle.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_GIT_TIMEOUT = 15.0


class GitError(RuntimeError):
    """Non-zero exit from a git call invoked with ``check=True``."""


# -----------------------------------------------------------------------------
# Git subprocess helper (hygiene mirrors tools/list_iterate_branches.run_git)
# -----------------------------------------------------------------------------


def run_git(
    args: list[str],
    *,
    cwd: Path,
    timeout: float = DEFAULT_GIT_TIMEOUT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command with consistent hygiene.

    - ``--no-pager`` prevents pager hangs.
    - ``-C <cwd>`` scopes the call to the requested repo.
    - ``shell=False`` + list argv — no injection surface.
    - ``encoding="utf-8", errors="replace"`` — safe on Windows locales.
    - ``TimeoutExpired`` kills + reaps so no zombie git.exe lingers.
    - ``check=True`` raises :class:`GitError` on non-zero exit.
    """
    # `encoding` and `errors` kwargs are available since Python 3.6 — the project requires 3.11+ (see pyproject.toml).
    # nosemgrep: python.lang.compatibility.python36.python36-compatibility-Popen1,python.lang.compatibility.python36.python36-compatibility-Popen2
    proc = subprocess.Popen(
        ["git", "--no-pager", "-C", str(cwd), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise
    if check and proc.returncode != 0:
        raise GitError(
            f"git {args[0] if args else '?'} failed "
            f"(exit {proc.returncode}): {err.strip()!r}"
        )
    return subprocess.CompletedProcess(["git", *args], proc.returncode, out, err)


# -----------------------------------------------------------------------------
# Worktree / main-repo detection
# -----------------------------------------------------------------------------


def resolve_git_dirs(root: Path) -> tuple[Path, Path]:
    """Return ``(git_dir, git_common_dir)`` as absolute resolved paths."""
    out = run_git(
        ["rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"],
        cwd=root,
    ).stdout
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if len(lines) != 2:
        raise GitError(f"unexpected rev-parse output for git dirs: {out!r}")
    return Path(lines[0]).resolve(), Path(lines[1]).resolve()


def is_worktree(root: Path) -> bool:
    """True when ``root`` is a *linked* worktree, not the main working tree.

    In the main repo ``--git-dir`` and ``--git-common-dir`` are the same path;
    in a linked worktree ``--git-dir`` points at ``.git/worktrees/<name>``.
    """
    git_dir, common = resolve_git_dirs(root)
    return git_dir != common


def main_repo_root(root: Path) -> Path:
    """Absolute path to the MAIN repo working tree (never a linked worktree)."""
    _, common = resolve_git_dirs(root)
    if common.name == ".git":
        return common.parent
    # Bare repo / unusual layout — fall back to this checkout's toplevel.
    return Path(run_git(["rev-parse", "--show-toplevel"], cwd=root).stdout.strip())

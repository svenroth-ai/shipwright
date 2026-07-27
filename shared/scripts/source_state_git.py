"""Resolve the code version a produced artifact was measured against.

The half of the artifact-state stamp (card ``trg-4d5b6a56``, FR-01.10) that is resolved
by **code** rather than declared by the caller: the HEAD commit, and whether tracked
files were modified relative to it. Split out of ``source_state.py`` so neither module
carries two subjects — that one owns the identifier's *shape*, this one answers *what
the state actually was*. The same seam the test modules are split along.

Every failure degrades to ``None`` rather than raising: a stamp that cannot determine
the code version must say so, never guess, and must never take down the producer that
called it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from source_state import SourceState, safe_run_id

_GIT_TIMEOUT_SECONDS = 10


def _git(args: list[str], cwd: Path) -> str | None:
    """Run git with an argument array (never a shell), bounded timeout.

    stdout, or ``None`` on any failure (missing binary, not a repo, timeout,
    non-zero exit). Callers degrade; they never propagate.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _porcelain_paths(line: str) -> Iterable[str]:
    """Path(s) named by one ``git status --porcelain`` line (``R  old -> new``
    counts both sides as touched)."""
    body = line[3:] if len(line) > 3 else ""
    if " -> " in body:
        for half in body.split(" -> ", 1):
            yield half.strip().strip('"')
    elif body:
        yield body.strip().strip('"')


def _repo_relative(root: Path, paths: Iterable[str]) -> set[str]:
    """Re-express ``paths`` relative to the repo root, the way git prints them."""
    top = _git(["rev-parse", "--show-toplevel"], root)
    base = Path(top.strip()) if top and top.strip() else root
    out: set[str] = set()
    for raw in paths:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            out.add(candidate.resolve().relative_to(base.resolve()).as_posix())
        except (ValueError, OSError):
            # Outside the repo: cannot be one of git's paths, so nothing to exclude.
            continue
    return out


def resolve_git_state(
    project_root: Path | str,
    *,
    run_id: str | None = None,
    exclude_paths: Iterable[str] = (),
) -> SourceState:
    """Resolve the state of the code at production time.

    ``commit`` is HEAD (full 40-hex), or ``None`` in a non-repo, an empty repo, or
    when git is unavailable. ``dirty`` means **tracked files modified relative to
    HEAD** (``--untracked-files=no``), ``None`` when git could not answer, with two
    deliberate narrowings: untracked files are ignored (a scratch file does not
    change which code ran), and ``exclude_paths`` drops named artifacts — callers
    pass the artifact they are about to stamp, since the stamp runs *after* it is
    written and without the exclusion ``dirty`` would be ``True`` every run.

    ``exclude_paths`` may be absolute or relative to ``project_root``; both are
    re-expressed relative to the **repository root** before matching, because that
    is what ``git status --porcelain`` prints. Without that step an exclusion
    silently fails to match whenever ``project_root`` is a subdirectory of the repo,
    and ``dirty`` degenerates to always-``True`` — the very failure the exclusion
    exists to prevent (external review, correctness/low).
    """
    root = Path(project_root)
    resolved_run = safe_run_id(run_id)

    head = _git(["rev-parse", "HEAD"], root)
    commit = head.strip() if head and head.strip() else None

    status = _git(["status", "--porcelain", "--untracked-files=no"], root)
    if status is None:
        dirty: bool | None = None
    else:
        excluded = _repo_relative(root, exclude_paths)
        dirty = False
        for line in status.splitlines():
            if not line.strip():
                continue
            paths = {p.replace("\\", "/") for p in _porcelain_paths(line)}
            if paths and paths <= excluded:
                continue
            dirty = True
            break

    return SourceState(run_id=resolved_run, commit=commit, dirty=dirty)


__all__ = ["resolve_git_state"]

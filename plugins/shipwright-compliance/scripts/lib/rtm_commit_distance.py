"""How far the manifest's ``source_commit`` is behind HEAD (``rtm_manifest_coverage``).

A git probe kept apart from the coverage arithmetic: list args, no shell, ``LC_ALL=C``
so git's messages stay classifiable on a localized machine.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rtm_manifest_read import _GIT_TIMEOUT_S

NOT_IN_HISTORY = -1  # commits_behind: the source commit is not in local history


def _git(project_root: str | Path, *args: str) -> subprocess.CompletedProcess | None:
    """``git -C <root> <args>`` (``LC_ALL=C``), or ``None`` when git cannot run at all."""
    env = {**os.environ, "LC_ALL": "C", "LANGUAGE": "C"}
    try:
        return subprocess.run(["git", "-C", str(project_root), *args], capture_output=True,
                              text=True, timeout=_GIT_TIMEOUT_S, check=False, env=env)
    except (OSError, subprocess.SubprocessError):
        return None


def commits_behind(project_root: str | Path, source_commit: str) -> int | None:
    """Commits between the manifest's ``source_commit`` and HEAD.

    :data:`NOT_IN_HISTORY` only when ``git cat-file -e <sha>^{commit}`` says the
    commit really is missing while HEAD exists (a shallow clone, a rewritten
    branch). ``None`` -- no WARN -- when git cannot answer: not a repo, git
    missing, a timeout, an unborn HEAD, any other error.
    """
    probe = _git(project_root, "cat-file", "-e", f"{source_commit}^{{commit}}")
    if probe is None:
        return None
    if probe.returncode != 0:
        if "Not a valid object name" not in (probe.stderr or ""):
            return None
        head = _git(project_root, "rev-parse", "-q", "--verify", "HEAD^{commit}")
        return NOT_IN_HISTORY if head is not None and head.returncode == 0 else None
    out = _git(project_root, "rev-list", "--count", f"{source_commit}..HEAD")
    try:
        return int(out.stdout.strip()) if out is not None and out.returncode == 0 else None
    except ValueError:
        return None

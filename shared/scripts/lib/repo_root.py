"""Fail-soft MAIN-repo-root resolver for advisory / fail-open hooks.

The bloat-marker PostToolUse recorder (``check_file_size``) and the Stop gate
(``bloat_gate_on_stop``) MUST key the marker / baseline / re-measure off the
SAME canonical MAIN repo root — never ``Path.cwd()``. A hook firing with
cwd != repo-root (a sub-package test run, monorepo auto-descent) would
otherwise write the marker into a nested ``.shipwright/locks/`` that the
root-anchored gitignore misses (the leak class ADR-089 hard-gated for
finalize). See ``conventions.md`` (iterate-2026-06-09; trg-7640bd14).

This is a thin fail-soft adapter over ``worktree_isolation.main_repo_root`` so
the hot-path hooks never brick. It lives in its OWN module — not appended to
``worktree_isolation.py`` — to avoid ratcheting that already-grandfathered
(>300 LOC) module past its bloat ceiling for a 6-line helper.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.worktree_isolation import GitError, main_repo_root


def main_repo_root_or(start: Path, fallback: Path | None = None) -> Path:
    """Return the MAIN working tree for ``start`` (resolving from any subdir AND
    from a linked worktree), or ``fallback`` (default ``start``) when git
    resolution fails — ``start`` not in a repo, git missing, timeout, or
    unexpected output. Every failure mode degrades to ``fallback`` so advisory
    hooks never break the tool flow."""
    try:
        return main_repo_root(start)
    except (GitError, OSError, subprocess.SubprocessError, ValueError):
        return fallback if fallback is not None else start

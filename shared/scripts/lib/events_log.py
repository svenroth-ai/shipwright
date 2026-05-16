"""Worktree-aware resolution of the ``shipwright_events.jsonl`` event log.

Single source of truth for *locating* the unified event log. The log is a
**repo-scoped** append-only journal. Under ``/shipwright-iterate`` worktree
isolation (see shipwright-iterate SKILL.md "Worktree Isolation") a run
executes inside an ephemeral linked worktree, but the canonical event log
lives next to the **main** repo. A literal ``project_root / EVENT_FILE``
from inside a worktree therefore reads/writes a throwaway copy that is
discarded on ``git worktree remove`` — F7 ``work_completed`` events never
reach the main log.

``resolve_events_path`` resolves the log via ``git rev-parse
--git-common-dir``: git consistently reports the *main* repo's ``.git``
directory even from inside a linked worktree, and its parent is the
canonical project root that owns the event log.

Relationship to ``shipwright-compliance``'s
``data_collector._resolve_events_path``
----------------------------------------------------------------------
This helper is the **shared-side SSoT**, modelled on that compliance-plugin
function (which stays separate — the compliance plugin is a distinct
distributable and cannot import ``shared/scripts/lib`` without a
cross-plugin path bootstrap). A parity test pins the two to the same
answer. This helper deliberately hardens two things the compliance copy
does not:

- It does **not** pass ``--path-format=absolute`` (a Git 2.31+ flag, Mar
  2021). Older git silently fails that flag, which would trigger the
  fallback and leave the worktree bug unfixed. Plain ``--git-common-dir``
  is resolved to an absolute path against ``project_root`` in Python —
  same answer, no git-version floor.
- When git is genuinely **broken** (binary absent, timeout) or returns an
  **unexpected layout**, it emits a ``warnings.warn`` diagnostic before
  falling back, so a worktree run whose git unexpectedly failed is visible
  rather than silently writing the throwaway worktree copy.

In a plain single-repo checkout (no linked worktree) the resolved path is
identical to ``project_root / EVENT_FILE`` — behavior is unchanged.
"""

from __future__ import annotations

import os
import subprocess
import warnings
from pathlib import Path

EVENT_FILE = "shipwright_events.jsonl"

# git path-resolution is a single fast call; cap it so a hung git cannot
# wedge an append.
_GIT_TIMEOUT_SECONDS = 15.0

# Environment variables that override git's repo discovery. If any of these
# leak in from the caller's environment, `git rev-parse` would resolve a
# DIFFERENT repo than ``cwd=project_root`` — silently writing the event log
# into the wrong repo. Strip them so resolution is pinned to project_root.
_GIT_DISCOVERY_OVERRIDES = ("GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE")


def _git_env() -> dict[str, str]:
    """Process environment with git repo-discovery overrides removed."""
    env = dict(os.environ)
    for var in _GIT_DISCOVERY_OVERRIDES:
        env.pop(var, None)
    return env


def resolve_events_path(project_root: Path | str) -> Path:
    """Return the path to ``shipwright_events.jsonl``, git-worktree-aware.

    From inside a linked git worktree this resolves to the **main** repo's
    event log; in a plain checkout — or when git is unavailable — it is
    identical to ``project_root / EVENT_FILE`` (behavior unchanged).

    A ``warnings.warn`` diagnostic is emitted only when git is *broken*
    (binary missing, timeout) or returns an *unexpected* layout. A plain
    "not a git repository" answer is silent: that is a definitive,
    no-data-loss result — a non-git project's log genuinely lives at
    ``project_root / EVENT_FILE``.
    """
    project_root = Path(project_root)
    fallback = project_root / EVENT_FILE

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=_git_env(),
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # git binary missing / un-spawnable / hung — we cannot tell whether
        # this is a worktree, so a fallback here MAY be silent data loss.
        warnings.warn(
            f"resolve_events_path: git unavailable for {project_root} "
            f"({exc!r}) — falling back to {fallback}. An iterate worktree "
            "run may write a throwaway event log.",
            stacklevel=2,
        )
        return fallback

    if proc.returncode != 0:
        # Definitive "not a git repository" — the fallback is correct, not
        # a failure. Silent by design (non-git projects + test tmp dirs).
        return fallback

    common_dir = proc.stdout.strip()
    if not common_dir:
        warnings.warn(
            f"resolve_events_path: `git rev-parse --git-common-dir` returned "
            f"empty output in {project_root} — falling back to {fallback}.",
            stacklevel=2,
        )
        return fallback

    common_path = Path(common_dir)
    if not common_path.is_absolute():
        # Without --path-format=absolute, `--git-common-dir` yields a path
        # relative to the git command's cwd, which we pinned to project_root.
        common_path = (project_root / common_path).resolve()

    # `--git-common-dir` returns the MAIN repo's .git directory; its parent
    # is the canonical project root that owns the event log. A linked
    # worktree's *git-dir* is `.git/worktrees/<name>`, but its *common* dir
    # is the top-level `.git` — so this is worktree-correct. Defensive: only
    # trust a path that actually ends in ".git".
    if common_path.name == ".git":
        return common_path.parent / EVENT_FILE

    warnings.warn(
        f"resolve_events_path: unexpected git-common-dir {str(common_path)!r} "
        f"(not a `.git` directory) for {project_root} — falling back to "
        f"{fallback}.",
        stacklevel=2,
    )
    return fallback

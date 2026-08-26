"""Location-only worktree-isolation check for campaign mode.

Split out of :mod:`worktree_isolation` (which was already at its bloat
baseline ceiling) rather than folded in — this predicate is deliberately a
NARROW subset of that module's fuller :func:`check_iterate_isolation._decide`
leak-guard: no run_id, no Step-1 snapshot, no main-tree diff. See
``plugins/shipwright-iterate/skills/iterate/references/campaign-worktree.md``
for the full rationale and the two call sites (campaign-mode.md step 3c,
sub-iterate-runner.md Step 1.0).
"""

from __future__ import annotations

from pathlib import Path

from lib.worktree_isolation import (
    WORKTREES_DIRNAME,
    GitError,
    is_under_worktrees,
    is_worktree,
    main_repo_root,
)


def worktree_location_error(project_root: Path) -> str:
    """"" if project_root is an isolated worktree, else why it is unsafe for
    further git commands."""
    try:
        worktree = is_worktree(project_root)
    except GitError as exc:
        return f"cannot resolve git context for {project_root}: {exc}"
    main_root = main_repo_root(project_root)
    if worktree and is_under_worktrees(project_root, main_root):
        return ""
    return (f"{project_root} is not an iterate worktree under "
            f"{main_root}/{WORKTREES_DIRNAME}/ — refusing to operate here.")

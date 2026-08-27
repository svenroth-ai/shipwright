"""Location-only worktree-isolation check for campaign mode.

Split out of :mod:`worktree_isolation` (which was already at its bloat
baseline ceiling) rather than folded in — this predicate is deliberately a
NARROW subset of that module's fuller :func:`check_iterate_isolation._decide`
leak-guard: no run_id, no Step-1 snapshot, no main-tree diff. See
``plugins/shipwright-iterate/skills/iterate/references/campaign-worktree.md``
for the full rationale and the two call sites (campaign-mode.md step 3c,
sub-iterate-runner.md Step 1.0).

``expected_campaign_slug`` (optional) adds an identity check on top of the
location check: proves ``project_root`` a worktree under ``.worktrees/`` is
not enough — a misdirected ``project_root`` pointing at a DIFFERENT, still
valid campaign worktree (a stale prior campaign, a sibling campaign) passes
that check unchanged.

Checked against the worktree DIRECTORY's basename (``campaign-{slug}``),
not the checked-out branch. `setup_iterate_worktree.py` names that directory
once, at creation, and it never changes for the campaign's whole lifetime;
the branch checked out INSIDE it does change (Step 1 of
`sub-iterate-runner.md` moves it to `iterate/campaign-{slug}-{sub_iterate_id}
-{desc}` per sub-iterate). A branch-prefix check was tried first and
rejected (external review of this same change): two campaigns whose slugs
are themselves a hyphenated extension of one another (`req3` vs `req3-04`)
are indistinguishable from a slug plus a sub-iterate suffix under a prefix
match, since both share the same `-`-separated shape. The directory basename
carries no such suffix, so this check is EXACT, not a narrowing heuristic.

Compared as the FULL resolved path (`main_root/.worktrees/campaign-{slug}`),
not the basename alone — a basename-only compare would let
`<main>/.worktrees/other/campaign-foo` (a nested directory sharing the right
name) pass. `Path.resolve()` consults the filesystem for an existing path, so
on a case-insensitive filesystem (Windows) a slug differing only in case
resolves to the same on-disk path and compares equal, while a case-sensitive
filesystem (Linux/macOS) correctly treats it as a different directory —
matching each platform's own notion of "the same path", not a hand-rolled
case rule.
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


def worktree_location_error(project_root: Path, *,
                             expected_campaign_slug: str | None = None) -> str:
    """Return "" if project_root is an isolated worktree, else a string
    describing why it is unsafe for further git commands.

    When ``expected_campaign_slug`` is given, also require the worktree
    DIRECTORY to be named ``campaign-{expected_campaign_slug}`` exactly (see
    module docstring — this is an exact check, not a prefix heuristic).
    """
    try:
        worktree = is_worktree(project_root)
    except GitError as exc:
        return f"cannot resolve git context for {project_root}: {exc}"
    main_root = main_repo_root(project_root)
    if not (worktree and is_under_worktrees(project_root, main_root)):
        return (f"{project_root} is not an iterate worktree under "
                f"{main_root}/{WORKTREES_DIRNAME}/ — refusing to operate here.")
    if expected_campaign_slug is not None:
        expected_name = f"campaign-{expected_campaign_slug}"
        actual_path = Path(project_root).resolve()
        expected_path = (Path(main_root) / WORKTREES_DIRNAME / expected_name).resolve()
        if actual_path != expected_path:
            return (f"{project_root} is worktree {actual_path.name!r}, expected "
                    f"{expected_name!r} at {expected_path} — this is a different "
                    "campaign's worktree.")
    return ""

"""Is the staged evidence about the code F11 is verifying? (the "this revision's" rule).

The provenance sidecar names the commit the evidence was staged at
(``head_commit``) and, since U5, the tree that was actually tested
(``tested_tree``, ``lib/worktree_tree.working_tree_id``): F0 runs on an
uncommitted tree, so the commit is only the base. Evidence describes the
verified commit when:

1. ``head_commit`` is the verified commit or an ancestor of it. Evidence staged
   on another branch, or before a rebase, describes other code;
2. a ``tested_tree`` fingerprint exists. Without one there is no way to tell
   the tested code from the committed code, so unfingerprinted evidence is
   stale; and
3. for every path THIS run changed (the tested tree against its base, plus the
   branch's own first-parent commits after it), the verified commit holds the
   same content as the tested tree. A review fix committed after staging, or an
   edit made after staging and folded into the F6 commit, shows up here.

Ignored on purpose: paths only a merge from the trunk brought in (another
unit's code, verified by its own run and by CI), and finalization records
(``review_diff_threshold.is_counted_path``), such as the campaign's 3f-bis
review-record commit. Residual gap: the fingerprint is taken when the reports
are staged, so an edit made between running the tests and staging them is not
seen. Stage right after F0 / F0.5.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.review_diff_threshold import is_counted_path  # noqa: E402

from .git_helpers import _run_git  # noqa: E402

__all__ = ["revision_problem"]

_T = 30.0


def _names(project_root: Path, *args: str) -> set[str] | None:
    rc, out, _ = _run_git(project_root, "-c", "core.quotePath=false", *args, timeout=_T)
    if rc != 0:
        return None
    return {p.strip() for p in out.splitlines() if p.strip() and is_counted_path(p.strip())}


def revision_problem(project_root: Path, head: str, tree: object, commit: str) -> str | None:
    """Why evidence staged at ``head`` over ``tree`` does not describe ``commit``, or ``None``."""
    rc, _, _ = _run_git(project_root, "merge-base", "--is-ancestor", head, commit, timeout=_T)
    if rc != 0:
        return (f"the evidence was staged at {head[:12]}, which is not the verified commit "
                f"{commit[:12]} or an ancestor of it (another branch, or staged before a rebase)")
    if not isinstance(tree, str) or not tree.strip():
        return ("the evidence carries no `tested_tree` fingerprint, so the tested code cannot be "
                "told apart from the committed code (staged by a pre-U5 evidence_drop?)")
    tested = _names(project_root, "diff", "--name-only", "--no-renames", head, tree)
    later = _names(project_root, "log", "--first-parent", "--no-merges", "--name-only", "--format=",
                   f"{head}..{commit}")
    differs = _names(project_root, "diff", "--name-only", "--no-renames", tree, commit)
    if tested is None or later is None or differs is None:
        return (f"git could not compare the tested tree {tree[:12]} with {commit[:12]} "
                "(fingerprint unreadable, or pruned by `git gc`)")
    changed = sorted(differs & (tested | later))
    if changed:
        return (f"{changed[0]!r} in {commit[:12]} is not what the staged results ran against "
                f"(tested tree {tree[:12]}): code changed after staging, e.g. a fix committed later"
                + (f", and {len(changed) - 1} more path(s)" if len(changed) > 1 else ""))
    return None

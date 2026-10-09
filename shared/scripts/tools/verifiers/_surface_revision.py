"""Is the staged evidence about the code F11 is verifying? (the "this revision's" rule).

The provenance sidecar names the commit the evidence was staged at
(``head_commit``) and, since U5, the tree that was actually tested
(``tested_tree``, ``lib/worktree_tree.working_tree_id``): F0 runs on an
uncommitted tree, so the commit is only the base. Without a ``tested_tree``
there is no way to tell the tested code from the committed code, so
unfingerprinted evidence is stale.

**The rule, when ``head_commit`` is the verified commit or an ancestor of it.**
The paths the branch itself owns are the ones the tested tree changed against
``head`` plus the ones the branch's own first-parent NON-merge commits in
``head..commit`` touched, plus the paths a first-parent trunk merge there
resolved by hand (a conflict: what the merge commit holds for it is the
branch's own write, ``git merge-tree`` names them). For each such path ``P`` the tested content
``tree:P`` is compared with ``L(P):P``, where ``L(P)`` is the newest of those
commits that touched ``P`` (``head`` when none did). F11 runs ``ensure_current``
(a merge from the trunk) before this check, so the verified commit itself may
carry a sibling unit's hunks in a file this branch also edited: comparing with
the branch's own last write of ``P`` leaves those hunks out, whether the unit
staged before or after its own commit. A review fix committed after staging,
or an amend, is that last write, so it still differs.

**When ``head_commit`` is not an ancestor** (a soft-reset consolidation of the
unit's commits, a rebase, evidence from another branch) there is no commit walk
to follow: the tested tree must equal the verified commit on every path the
branch changed (``measure_diff``'s paths) and every path the tested tree
changed against ``head``.

Never counted: tests and prose (``_surface_detect.is_test_or_prose``; they
cannot make code evidence stale), finalization records, and a path present
only in the tested tree, absent from both ``head`` and the verified commit (a
stray untracked file such as a test-run leak). Strays are named in the note.

Residual gaps (ADR): the fingerprint is taken at staging, which
``evidence_drop.stage`` bounds by refusing reports older than the code. An
octopus merge in ``head..commit`` cannot be replayed, so it is unreadable and
fails closed. A merge of a NON-trunk side branch (or an updated stacked parent)
is not told apart from a trunk merge: its own commits are not first-parent, and
a clean replay shows no hand edit, so code it brought in reads as the trunk's.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from ._surface_detect import is_test_or_prose  # noqa: E402
from ._surface_git import object_ids  # noqa: E402
from .git_helpers import _run_git  # noqa: E402

__all__ = ["revision_problem"]


class _MergeTreeUnsupported(Exception):
    """``git merge-tree --write-tree`` is unavailable (git < 2.38) or could not replay a merge; the text says which."""

_T = 30.0
_GIT_FAILED = "git could not compare the tested tree {tree} with {commit} (fingerprint unreadable, or pruned by `git gc`)"


def _owned(path: str) -> bool:
    return bool(path) and not is_test_or_prose(path)


def _tested_paths(project_root: Path, head: str, tree: str) -> set[str] | None:
    rc, out, _ = _run_git(project_root, "-c", "core.quotePath=false", "diff", "--name-only",
                          "--no-renames", head, tree, timeout=_T)
    return {p.strip() for p in out.splitlines() if _owned(p.strip())} if rc == 0 else None


def _resolutions(project_root: Path, head: str, commit: str) -> dict[str, str] | None:
    """``{path: newest first-parent merge commit in head..commit that changed it by hand}``.

    Each merge is replayed (``git merge-tree``); every path where the recorded merge
    differs from git's own automatic merge was resolved or edited by hand: a conflict
    (the replayed tree holds markers) or an edit inside a cleanly merged file.
    ``None`` when git failed or a merge has other than two parents.
    """
    rc, out, _ = _run_git(project_root, "rev-list", "--first-parent", "--merges", "--parents",
                          f"{head}..{commit}", timeout=_T)
    if rc != 0:
        return None
    owners: dict[str, str] = {}
    for line in out.splitlines():
        shas = line.split()
        if not shas:
            continue
        if len(shas) != 3:
            return None
        rc, replay, err = _run_git(project_root, "merge-tree", "--write-tree", "-z", shas[1], shas[2], timeout=_T)
        if rc == 129:  # usage error: this git has no --write-tree
            raise _MergeTreeUnsupported("this git is older than 2.38, so a trunk merge's hand edits cannot be "
                                        "replayed (`git merge-tree --write-tree`); upgrade git to verify this branch")
        if rc not in (0, 1):  # 1 = conflicts, the case this exists for
            raise _MergeTreeUnsupported(f"git merge-tree could not replay the merge {shas[0][:12]} "
                                        f"(exit {rc}: {err.strip()[:120]}; unrelated history or a shallow clone?)")
        replayed = replay.split(chr(0), 1)[0].strip()
        rc, diff, _ = _run_git(project_root, "-c", "core.quotePath=false", "diff", "--name-only", "--no-renames",
                               replayed, f"{shas[0]}^{{tree}}", timeout=_T)
        if rc != 0:
            return None
        for name in diff.splitlines():
            if _owned(name.strip()):
                owners.setdefault(name.strip(), shas[0])  # newest first: the first sighting wins
    return owners


def _last_writes(project_root: Path, head: str, commit: str) -> dict[str, str] | None:
    """``{path: newest first-parent commit in head..commit that wrote it}``.

    A write is a non-merge commit touching the path, or a merge that hand-resolved a conflict in it.
    """
    rc, out, _ = _run_git(project_root, "-c", "core.quotePath=false", "log", "--first-parent",
                          "--no-merges", "--no-renames", "--name-only", "--format=%x00%H",
                          f"{head}..{commit}", timeout=_T)
    resolved = _resolutions(project_root, head, commit)
    rc_order, order, _ = _run_git(project_root, "rev-list", "--first-parent", f"{head}..{commit}", timeout=_T)
    if rc != 0 or resolved is None or rc_order != 0:
        return None
    age = {sha: n for n, sha in enumerate(order.split())}  # 0 = newest
    owners: dict[str, str] = {}
    sha = ""
    for line in out.splitlines():
        if line.startswith("\0"):
            sha = line[1:].strip()
        elif sha and _owned(line.strip()):
            owners.setdefault(line.strip(), sha)  # newest first: the first sighting wins
    for path, merge in resolved.items():
        if merge not in age or (path in owners and owners[path] not in age):
            return None  # an ordering git did not give us is not read as "newest"
        if path not in owners or age[merge] < age[owners[path]]:
            owners[path] = merge
    return owners


def _compare(project_root: Path, tree: str, head: str, commit: str,
             refs: dict[str, str]) -> tuple[list[str], list[str]] | None:
    """``(differing paths, stray paths)``; ``refs`` maps each path to the revision it must match."""
    specs = [f"{rev}:{p}" for p, ref in refs.items() for rev in (tree, ref, head, commit)]
    ids = object_ids(project_root, sorted(set(specs)))
    if ids is None:
        return None
    differs, strays = [], []
    for path, ref in sorted(refs.items()):
        tested = ids[f"{tree}:{path}"]
        if tested is not None and ids[f"{head}:{path}"] is None and ids[f"{commit}:{path}"] is None:
            strays.append(path)  # only in the tested tree: an untracked stray, not the branch's code
        elif tested != ids[f"{ref}:{path}"]:
            differs.append(path)
    return differs, strays


def _stray_note(strays: list[str]) -> str:
    if not strays:
        return ""
    return (f"; ignored {len(strays)} tested-only path(s) absent from the commit "
            f"(untracked strays, e.g. {strays[0]!r})")


def revision_problem(project_root: Path, head: str, tree: object, commit: str,
                     branch_paths: list[str] | tuple[str, ...] = ()) -> tuple[str | None, str]:
    """``(problem, note)``: why evidence staged at ``head`` over ``tree`` does not describe ``commit``.

    ``branch_paths`` are the branch's changed paths (``measure_diff``), used only
    when ``head`` is not an ancestor of ``commit``.
    """
    if not isinstance(tree, str) or not tree.strip():
        return ("the evidence carries no `tested_tree` fingerprint, so the tested code cannot be "
                "told apart from the committed code (staged by a pre-U5 evidence_drop?)"), ""
    failed = _GIT_FAILED.format(tree=tree[:12], commit=commit[:12])
    tested = _tested_paths(project_root, head, tree)
    if tested is None:
        return failed, ""
    rc, _, _ = _run_git(project_root, "merge-base", "--is-ancestor", head, commit, timeout=_T)
    if rc != 0:
        paths = tested | {p for p in branch_paths if _owned(p)}
        compared = _compare(project_root, tree, head, commit, {p: commit for p in paths})
        if compared is None:
            return failed, ""
        differs, strays = compared
        if differs:
            return (f"the evidence was staged at {head[:12]}, which is not the verified commit "
                    f"{commit[:12]} or an ancestor of it (another branch, a rebase, or a "
                    f"consolidation), and the tested tree differs from it at {differs[0]!r}"), ""
        return None, (f"; staged at {head[:12]}, not an ancestor (consolidated?), but the tested "
                      f"tree equals the commit on all {len(paths)} branch path(s)") + _stray_note(strays)
    try:
        owners = _last_writes(project_root, head, commit)
    except _MergeTreeUnsupported as exc:
        return str(exc), ""
    if owners is None:
        return failed, ""
    refs = {p: owners.get(p, head) for p in tested | set(owners)}
    compared = _compare(project_root, tree, head, commit, refs)
    if compared is None:
        return failed, ""
    differs, strays = compared
    if differs:
        return (f"{differs[0]!r} in {refs[differs[0]][:12]} is not what the staged results ran "
                f"against (tested tree {tree[:12]}): code changed after staging, e.g. a fix "
                "committed later or an amend"
                + (f", and {len(differs) - 1} more path(s)" if len(differs) > 1 else "")), ""
    return None, _stray_note(strays)

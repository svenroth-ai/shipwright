"""Check a no-FR ``change_type`` label against what the iterate actually changed.

The FR-gate (:func:`lib.fr_gates.fr_or_change_type_gate_error`) accepts
``change_type`` + ``none_reason`` in place of an FR. Without this check the
label was self-reported and never compared with the work, so a runtime change
could call itself ``tooling`` and skip requirement linkage entirely.

**The diff.** Fork point to the **working tree, untracked files included**,
because F5b records the event before F6 commits. Rename detection is on so both
sides of a move are judged: moving ``src/app.py`` to ``docs/app.md`` deletes
runtime code, and a ``docs`` label does not cover that. Deletions are judged.
``ls-files`` runs with ``--full-name`` so a project inside a larger repository
gets repo-relative paths, like ``git diff``, and the rebase onto the project
root keeps them instead of dropping them.

**The fork point.** Remote trunk names first (``origin/HEAD``, ``origin/main``,
``origin/master``); local ``main`` / ``master`` only when no remote name
resolves. A remote name that resolves but shares no history with ``HEAD`` (an
orphaned or rewritten trunk) REFUSES rather than falling through to a local
name, which may sit at ``HEAD`` and hide committed work. Among the names of the
winning tier, the narrowest merge-base (the one every other is an ancestor
of), so a stale ``origin/master`` after a rename cannot widen the range.

**The shape** is read from the fork-point tree (``git cat-file -e``), not the
working tree, so a change cannot widen its own labels by adding the monorepo
markers. Unborn ``HEAD`` has no fork point and is judged ``generic``.

**Outcomes.** Not a git repository: nothing to compare, so the event is allowed
and a WARNING is printed. A missing git binary counts as "not a repository"
only when no ``.git`` exists at or above the project root. git present but the
diff unobtainable (no trunk name resolves, git fails, unreadable output):
REFUSED, with a repair. Unknown is never read as clean. Only the no-FR branch
is checked: an event that names an FR is not using the exemption.

**Accepted limits.** Classification is by path, so an untracked file is judged
by where it is, not by what it contains. Under the ``stacked`` campaign
strategy the fork point is the trunk, so a predecessor unit's committed paths
count against this unit's label: that fails closed, and the refusal names the
paths (resolving the parent branch like ``git_helpers._branch_base_commit`` is
not cheap here, because the stacked parent is not a trunk name).
"""

from __future__ import annotations

import sys
from pathlib import Path

from lib.change_type_paths import SHAPE_GENERIC, SHAPE_MARKERS, SHAPE_SHIPWRIGHT_MONOREPO, unclassified_paths
from lib.fr_classification import CHANGE_TYPE_VALUES, is_non_empty_fr_list
from lib.git_name_status import NameStatusError, parse as parse_name_status
from lib.requirement_impact_git import (
    _GitBroke, _GitUnavailable, _has_commits, _is_repo, _listed_paths, _project_prefix, _resolve, _run, _stderr,
)

__all__ = ["LOCAL_TRUNKS", "REMOTE_TRUNKS", "DiffUnavailable", "change_type_diff_error", "iterate_diff",
           "shape_at"]

REMOTE_TRUNKS = ("origin/HEAD", "origin/main", "origin/master")
LOCAL_TRUNKS = ("main", "master")

_MAX_LISTED = 12


class DiffUnavailable(Exception):
    """git is present but could not say what this iterate changed."""


def _is_ancestor(root: Path, other: str, base: str) -> bool:
    """``base`` contains ``other`` (``other`` is an ancestor of or equal to ``base``)."""
    result = _run(root, ["rev-list", "--count", f"{base}..{other}"])
    if result.returncode != 0:  # a git fault is not an answer about ordering
        raise DiffUnavailable(f"git rev-list failed: {_stderr(result)}")
    return result.stdout.strip() == "0"


def _narrowest(root: Path, names: tuple[str, ...]) -> tuple[str, str] | None:
    """``(merge-base sha, ref name)`` of the narrowest base among ``names``, or ``None``.

    ``None`` only when no name resolves. A name that resolves without a
    merge-base, while no other name of the tier yields one, raises.
    """
    bases: dict[str, str] = {}
    unrelated: list[str] = []
    for name in names:
        result = _run(root, ["merge-base", name, "HEAD"])
        sha = result.stdout.strip()
        if result.returncode == 0 and sha:
            bases.setdefault(sha, name)
        elif _resolve(root, name):
            unrelated.append(name)
    for base, name in bases.items():
        if all(_is_ancestor(root, other, base) for other in bases if other != base):
            return base, name
    if bases:
        raise DiffUnavailable(f"the trunk refs {', '.join(bases.values())} share no ordering; "
                              "refusing to guess the fork point")
    if unrelated:
        raise DiffUnavailable(
            f"the trunk ref(s) {', '.join(unrelated)} resolve but share no history with HEAD "
            "(orphaned or rewritten trunk, or a shallow clone); refusing to fall back to another ref. Re-fetch the "
            "trunk (`git fetch origin <trunk>`) or rebase this branch onto it")
    return None


def _fork_point(root: Path) -> tuple[str, str]:
    found = _narrowest(root, REMOTE_TRUNKS) or _narrowest(root, LOCAL_TRUNKS)
    if found is None:
        raise DiffUnavailable(
            f"no trunk ref resolves ({', '.join(REMOTE_TRUNKS + LOCAL_TRUNKS)}); fetch the trunk "
            "(`git fetch origin <trunk>`) so the change can be compared with its fork point")
    return found


def _has_dot_git(root: Path) -> bool:
    try:
        resolved = root.resolve()
        return any((d / ".git").exists() for d in (resolved, *resolved.parents))
    except OSError:
        return True  # cannot tell: treat as a repository, so the caller refuses


def shape_at(project_root, base: str | None) -> str:
    """The project shape in the fork-point tree ``base``; ``generic`` without one."""
    if not base:
        return SHAPE_GENERIC
    root = Path(project_root)
    prefix = _project_prefix(root)
    for rel, is_dir in SHAPE_MARKERS:
        spec = f"{base}:{prefix + '/' if prefix else ''}{rel}"
        kind = _run(root, ["cat-file", "-t", spec])
        if kind.returncode != 0 or kind.stdout.strip() != ("tree" if is_dir else "blob"):
            return SHAPE_GENERIC
    return SHAPE_SHIPWRIGHT_MONOREPO


def iterate_diff(project_root) -> dict | None:
    """``{paths, base, base_ref}`` since the fork point; ``None`` = not a repo.

    Raises :class:`DiffUnavailable` when git exists but cannot answer.
    """
    root = Path(project_root)
    try:
        if not root.is_dir() or not _is_repo(root):
            return None
        prefix = _project_prefix(root)
        untracked = _run(root, ["ls-files", "--full-name", "--others", "--exclude-standard", "-z"])
        if untracked.returncode != 0:
            raise DiffUnavailable(f"git ls-files failed: {_stderr(untracked)}")
        paths = _listed_paths(untracked.stdout, prefix)
        if not _has_commits(root):  # unborn HEAD: everything present is new
            listed = _run(root, ["ls-files", "--full-name", "--cached", "-z"])
            if listed.returncode != 0:
                raise DiffUnavailable(f"git ls-files failed: {_stderr(listed)}")
            return {"paths": sorted(set(paths + _listed_paths(listed.stdout, prefix))),
                    "base": None, "base_ref": "unborn HEAD"}
        base, base_ref = _fork_point(root)
        diff = _run(root, ["diff", "--name-status", "-z", "-M", base, "--"])
        if diff.returncode != 0:
            raise DiffUnavailable(f"git diff failed: {_stderr(diff)}")
        buckets = parse_name_status(diff.stdout, prefix)
    except _GitUnavailable as exc:
        if root.is_dir() and _has_dot_git(root):
            raise DiffUnavailable(f"git is not runnable but {root} is inside a repository: {exc}") from exc
        return None
    except (_GitBroke, NameStatusError) as exc:
        raise DiffUnavailable(str(exc)) from exc
    changed = paths + buckets["added_modified"] + buckets["deleted"] + buckets["renamed"]
    return {"paths": sorted(set(changed)), "base": base, "base_ref": base_ref}


def change_type_diff_error(event, project_root, caller: str) -> dict | None:
    """Error dict when a no-FR ``change_type`` does not cover the iterate's diff."""
    if not isinstance(event, dict):
        return None
    if event.get("type") != "work_completed" or event.get("source") != "iterate":
        return None
    change_type = event.get("change_type")
    if change_type not in CHANGE_TYPE_VALUES:
        return None  # absent, or already refused by the classification gate
    if is_non_empty_fr_list(event.get("affected_frs")) or is_non_empty_fr_list(event.get("new_frs")):
        return None
    try:
        diff = iterate_diff(project_root)
        shape = shape_at(project_root, diff["base"]) if diff else SHAPE_GENERIC
    except (DiffUnavailable, _GitBroke, _GitUnavailable) as exc:
        return {"error": "change_type_diff_unavailable", "detail": (
            f"change_type={change_type!r} cannot be checked against the diff: {exc}. "
            "Repair git, or link the FR(s) this change touches with --affected-frs.")}
    if diff is None:
        print(f"[{caller}] WARNING: not a git repository - change_type={change_type!r} "
              "is NOT checked against the diff.", file=sys.stderr)
        return None
    outside = unclassified_paths(diff["paths"], change_type, shape)
    if not outside:
        return None
    shown = ", ".join(outside[:_MAX_LISTED]) + (f" (+{len(outside) - _MAX_LISTED} more)" if len(outside) > _MAX_LISTED else "")
    return {"error": "change_type_not_covered_by_diff", "detail": (
        f"change_type={change_type!r} does not cover {len(outside)} changed path(s) "
        f"(project shape {shape}, diff since {diff['base_ref']}): {shown}. A no-FR label must "
        "describe the whole diff: link the FR(s) the change touches (--affected-frs / --new-frs) "
        "or choose the label that covers these paths (lib/change_type_paths.py lists them).")}

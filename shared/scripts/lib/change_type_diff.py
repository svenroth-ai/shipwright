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

**A stacked campaign unit** measures only its own work. Its branch sits on the
previous unit's branch, so the trunk fork point would also count the stack below
it. The campaign runner names that parent in the event's ``stack_base_ref``
(``lib.branch_base.resolve_base_branch``); the diff then starts at it. The ref is
resolved in the branch namespaces only (a tag cannot shadow it) and accepted only
when it is an ``iterate/*`` unit branch (local or ``origin/``) that is an ancestor
of ``HEAD`` and not the unit's own branch; anything else REFUSES. The project
shape is still read from the trunk fork point, so a parent branch cannot widen the
labels. The unit's paths are those changed since the parent AND since the trunk
fork point, so trunk merged into the unit later drops out instead of over-flagging. The stack below was judged by
its own unit's gate, so it is not judged again.

**Accepted limits.** A stacked child that reverts the parent's change back to the
trunk content drops that path from its own diff. Classification is by path, so an untracked file is judged
by where it is, not by what it contains. ``stack_base_ref`` is stated by the
runner, not derived: an agent could point it at an ancestor unit branch of its
own making and so exempt the commits below it. Bounded by the ``iterate/*`` and
ancestor checks; nothing re-checks the label later.
"""

from __future__ import annotations

import re
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
_UNIT_BRANCH = re.compile(r"(?:origin/)?iterate/[A-Za-z0-9._/-]+\Z")


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


def _stack_base(root: Path, ref: str) -> tuple[str, str]:
    """``(sha, ref)`` of a stacked unit's parent branch, or raise: it must be an ancestor of HEAD."""
    if not _UNIT_BRANCH.match(ref) or ".." in ref:
        raise DiffUnavailable(f"stack_base_ref {ref!r} is not an iterate/* unit branch; refusing to start the diff there")
    # explicit namespaces: a tag named like the branch must not shadow it
    sha = _resolve(root, f"refs/remotes/{ref}" if ref.startswith("origin/") else f"refs/heads/{ref}")
    if not sha:
        raise DiffUnavailable(f"stack_base_ref {ref!r} does not resolve; fetch the parent unit's branch")
    if _run(root, ["merge-base", "--is-ancestor", sha, "HEAD"]).returncode != 0:
        raise DiffUnavailable(f"stack_base_ref {ref!r} is not an ancestor of HEAD; refusing to start the diff there")
    current = _run(root, ["symbolic-ref", "--short", "HEAD"]).stdout.strip()
    if not current:
        raise DiffUnavailable("HEAD is detached, so the unit's own branch cannot be told from stack_base_ref")
    if ref in (current, f"origin/{current}"):  # not sha == HEAD: a unit with no commit yet legitimately sits on its parent
        raise DiffUnavailable(f"stack_base_ref {ref!r} is this unit's own branch; name the PARENT unit's branch")
    if _run(root, ["merge-base", _fork_point(root)[0], sha]).returncode != 0:  # shares no history with the trunk
        raise DiffUnavailable(f"stack_base_ref {ref!r} shares no history with the trunk; refusing to start the diff there")
    return sha, ref


def iterate_diff(project_root, stack_base: str | None = None) -> dict | None:
    """``{paths, base, base_ref}`` since the fork point (or ``stack_base``); ``None`` = not a repo.

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
                    "base": None, "base_ref": "unborn HEAD", "shape_base": None}
        base, base_ref = _stack_base(root, stack_base) if stack_base else _fork_point(root)
        shape_base = _fork_point(root)[0] if stack_base else base  # a parent branch cannot widen the labels
        diff = _run(root, ["diff", "--name-status", "-z", "-M", base, "--"])
        if diff.returncode != 0:
            raise DiffUnavailable(f"git diff failed: {_stderr(diff)}")
        buckets = parse_name_status(diff.stdout, prefix)
        trunk_side = None
        if stack_base:  # the unit's own paths: changed since the parent AND since the trunk (a trunk merge drops out)
            wide = _run(root, ["diff", "--name-status", "-z", "-M", shape_base, "--"])
            if wide.returncode != 0:
                raise DiffUnavailable(f"git diff failed: {_stderr(wide)}")
            trunk_side = {p for names in parse_name_status(wide.stdout, prefix).values() for p in names}
    except _GitUnavailable as exc:
        if root.is_dir() and _has_dot_git(root):
            raise DiffUnavailable(f"git is not runnable but {root} is inside a repository: {exc}") from exc
        return None
    except (_GitBroke, NameStatusError) as exc:
        raise DiffUnavailable(str(exc)) from exc
    changed = buckets["added_modified"] + buckets["deleted"] + buckets["renamed"]
    if trunk_side is not None:
        changed = [p for p in changed if p in trunk_side]
    changed = paths + changed
    return {"paths": sorted(set(changed)), "base": base, "base_ref": base_ref, "shape_base": shape_base}


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
        stack = event.get("stack_base_ref")
        if isinstance(stack, str) and stack.strip() and not (event.get("campaign") and event.get("sub_iterate_id")):
            raise DiffUnavailable("stack_base_ref is only accepted from a campaign unit (the event names no campaign / sub_iterate_id)")
        diff = iterate_diff(project_root, stack.strip() if isinstance(stack, str) and stack.strip() else None)
        shape = shape_at(project_root, diff["shape_base"]) if diff else SHAPE_GENERIC
    except (DiffUnavailable, _GitBroke, _GitUnavailable) as exc:
        return {"error": "change_type_diff_unavailable", "detail": (
            f"change_type={change_type!r} cannot be checked against the diff: {exc}. "
            + ("Fix stack_base_ref to the PARENT unit's branch (omit it for the first stacked unit), or link the FR(s)."
               if "stack_base_ref" in str(exc) else "Repair git, or link the FR(s) this change touches with --affected-frs."))}
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

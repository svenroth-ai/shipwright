"""Check a no-FR ``change_type`` label against what the iterate actually changed.

The FR-gate (:func:`lib.fr_gates.fr_or_change_type_gate_error`) accepts
``change_type`` + ``none_reason`` in place of an FR. Without this check the
label was self-reported and never compared with the work, so a runtime change
could call itself ``tooling`` and skip requirement linkage entirely.

**The diff.** Fork point to the **working tree, untracked files included**,
because F5b records the event before F6 commits. Rename detection is on so both
sides of a move are judged: moving ``src/app.py`` to ``docs/app.md`` deletes
runtime code, and a ``docs`` label does not cover that. Deletions are judged.

**The fork point.** Remote trunk names first (``origin/HEAD``, ``origin/main``,
``origin/master``); local ``main`` / ``master`` only when no remote name
resolves. Among the names of the winning tier, the narrowest merge-base (the
one every other is an ancestor of), so a stale ``origin/master`` after a
rename cannot widen the range. Remote-first because a local ``main`` advanced
to ``HEAD`` would otherwise be the narrowest base and hide committed work.

**Outcomes.** Not a git repository: nothing to compare, so the event is allowed
and a WARNING is printed. git present but the diff unobtainable (no trunk name
resolves, git fails, unreadable output): REFUSED, with a repair. Unknown is
never read as clean. Only the no-FR branch is checked: an event that names an
FR is not using the exemption. Residual gap: classification is by path, so an
untracked file is judged by where it is, not by what it contains.
"""

from __future__ import annotations

import sys
from pathlib import Path

from lib.change_type_paths import detect_shape, unclassified_paths
from lib.fr_classification import CHANGE_TYPE_VALUES, is_non_empty_fr_list
from lib.git_name_status import NameStatusError, parse as parse_name_status
from lib.requirement_impact_git import (
    _GitBroke, _GitUnavailable, _has_commits, _is_repo, _listed_paths, _project_prefix, _run, _stderr,
)

__all__ = ["LOCAL_TRUNKS", "REMOTE_TRUNKS", "DiffUnavailable", "change_type_diff_error", "iterate_diff"]

REMOTE_TRUNKS = ("origin/HEAD", "origin/main", "origin/master")
LOCAL_TRUNKS = ("main", "master")

_MAX_LISTED = 12


class DiffUnavailable(Exception):
    """git is present but could not say what this iterate changed."""


def _narrowest(root: Path, names: tuple[str, ...]) -> tuple[str, str] | None:
    """``(merge-base sha, ref name)`` of the narrowest base among ``names``, or ``None``."""
    bases: dict[str, str] = {}
    for name in names:
        result = _run(root, ["merge-base", name, "HEAD"])
        sha = result.stdout.strip()
        if result.returncode == 0 and sha:
            bases.setdefault(sha, name)
    def _is_ancestor(other: str, base: str) -> bool:
        result = _run(root, ["rev-list", "--count", f"{base}..{other}"])
        if result.returncode != 0:  # a git fault is not an answer about ordering
            raise DiffUnavailable(f"git rev-list failed: {_stderr(result)}")
        return result.stdout.strip() == "0"

    for base, name in bases.items():
        if all(_is_ancestor(other, base) for other in bases if other != base):
            return base, name
    if bases:
        raise DiffUnavailable(f"the trunk refs {', '.join(bases.values())} share no ordering; "
                              "refusing to guess the fork point")
    return None


def _fork_point(root: Path) -> tuple[str, str]:
    found = _narrowest(root, REMOTE_TRUNKS) or _narrowest(root, LOCAL_TRUNKS)
    if found is None:
        raise DiffUnavailable(
            f"no trunk ref resolves ({', '.join(REMOTE_TRUNKS + LOCAL_TRUNKS)}); fetch the trunk "
            "(`git fetch origin <trunk>`) so the change can be compared with its fork point")
    return found


def iterate_diff(project_root) -> dict | None:
    """``{paths, base, base_ref}`` since the fork point; ``None`` = not a repo.

    Raises :class:`DiffUnavailable` when git exists but cannot answer.
    """
    root = Path(project_root)
    try:
        if not root.is_dir() or not _is_repo(root):
            return None
        prefix = _project_prefix(root)
        untracked = _run(root, ["ls-files", "--others", "--exclude-standard", "-z"])
        if untracked.returncode != 0:
            raise DiffUnavailable(f"git ls-files failed: {_stderr(untracked)}")
        paths = _listed_paths(untracked.stdout, prefix)
        if not _has_commits(root):  # unborn HEAD: everything present is new
            listed = _run(root, ["ls-files", "--cached", "-z"])
            if listed.returncode != 0:
                raise DiffUnavailable(f"git ls-files failed: {_stderr(listed)}")
            return {"paths": sorted(set(paths + _listed_paths(listed.stdout, prefix))),
                    "base": None, "base_ref": "unborn HEAD"}
        base, base_ref = _fork_point(root)
        diff = _run(root, ["diff", "--name-status", "-z", "-M", base, "--"])
        if diff.returncode != 0:
            raise DiffUnavailable(f"git diff failed: {_stderr(diff)}")
        buckets = parse_name_status(diff.stdout, prefix)
    except _GitUnavailable:
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
    except DiffUnavailable as exc:
        return {"error": "change_type_diff_unavailable", "detail": (
            f"change_type={change_type!r} cannot be checked against the diff: {exc}. "
            "Repair git, or link the FR(s) this change touches with --affected-frs.")}
    if diff is None:
        print(f"[{caller}] WARNING: not a git repository - change_type={change_type!r} "
              "is NOT checked against the diff.", file=sys.stderr)
        return None
    shape = detect_shape(project_root)
    outside = unclassified_paths(diff["paths"], change_type, shape)
    if not outside:
        return None
    shown = ", ".join(outside[:_MAX_LISTED]) + (f" (+{len(outside) - _MAX_LISTED} more)" if len(outside) > _MAX_LISTED else "")
    return {"error": "change_type_not_covered_by_diff", "detail": (
        f"change_type={change_type!r} does not cover {len(outside)} changed path(s) "
        f"(project shape {shape}, diff since {diff['base_ref']}): {shown}. A no-FR label must "
        "describe the whole diff: link the FR(s) the change touches (--affected-frs / --new-frs) "
        "or choose the label that covers these paths (lib/change_type_paths.py lists them).")}

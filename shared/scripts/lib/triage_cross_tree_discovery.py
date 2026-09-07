"""Locate sibling worktrees and name their checked-out branch.

Split out of :mod:`lib.triage_cross_tree` (which folds their content into a
main tree's own read) purely to keep that module under its line guideline —
the two halves are read together; see that module's docstring for WHY this
fold exists and its BOUNDARY / design-constraints sections.

**Ordinary file reads, no git subprocess.** ``main``-vs-``worktree`` and a
worktree's checked-out branch are both derived from ``.git`` file contents
(a linked worktree's ``.git`` is a FILE naming its admin dir, whose ``HEAD``
names the branch), never a ``git`` call — a subprocess per
``read_all_items`` call would be the wrong trade for a fact that never
changes mid-process. A non-absolute ``gitdir:`` target (relative worktree
paths, git >= 2.48) is resolved against the worktree's own directory, not
the process CWD, so that config can't silently disable every sibling at once
(Stage-3 doubt review, finding 7).

**Not cached — walked fresh on every call, deliberately** (PR #684 review
round). An earlier version memoized the walk on ``(.worktrees path, its
mtime)``, but a sibling *already* in ``.worktrees`` gaining a
``triage.jsonl`` after the first scan, or switching its checked-out branch
(``.git``/``HEAD`` rewritten), changes neither ``.worktrees``' own mtime nor
its listing — so that cache could report a sibling as absent, or under its
old branch, for the rest of the process. The walk itself is cheap (one
``iterdir`` plus, per sibling, an ``is_file`` check and up to two small text
reads for branch identity) — nothing here is the "84 sibling worktrees,
thousand-record logs" cost :func:`lib.triage_cross_tree._cached_records`
exists to amortize; that per-file PARSE is cached, this walk is not.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["sibling_worktree_logs"]

_SHIPWRIGHT_DIR = ".shipwright"
_TRIAGE_FILE = "triage.jsonl"
_WORKTREES_DIRNAME = ".worktrees"


def _is_main_tree(root: Path) -> bool:
    """True iff ``root`` is a main working tree, not a linked git worktree.

    A linked worktree's ``.git`` is a FILE (``gitdir: <path>``); the main
    tree's is a directory. Pure filesystem check.
    """
    return (root / ".git").is_dir()


def _branch_name(worktree_dir: Path) -> str | None:
    """Branch checked out in ``worktree_dir``, or ``None`` if it cannot be named
    (not a linked worktree, unreadable admin dir, or a detached ``HEAD``).

    Both reads are plain files: the worktree's own ``.git`` names its admin
    directory (``.git/worktrees/<name>``), whose ``HEAD`` holds either
    ``ref: refs/heads/<branch>`` or a raw commit SHA (detached).
    """
    git_marker = worktree_dir / ".git"
    try:
        text = git_marker.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    prefix = "gitdir:"
    line = next(
        (ln for ln in text.splitlines() if ln.strip().startswith(prefix)), None,
    )
    if line is None:
        return None
    admin_dir = Path(line.split(":", 1)[1].strip())
    if not admin_dir.is_absolute():
        # git >= 2.48 / worktree.useRelativePaths can write a relative
        # target; resolve it against the worktree's own directory, never the
        # process CWD, or every sibling silently loses this feature at once.
        admin_dir = (worktree_dir / admin_dir).resolve()
    try:
        head = (admin_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not head.startswith("ref:"):
        return None  # detached HEAD — no branch to name
    return head[len("ref:") :].strip().removeprefix("refs/heads/")


def sibling_worktree_logs(project_root: Path | str) -> list[tuple[str, Path]]:
    """``(branch, path)`` for every sibling worktree's TRACKED triage log.

    Empty unless ``project_root`` is the MAIN tree. A sibling directory with
    no tracked log, or whose branch cannot be named, is skipped rather than
    guessed at — reporting nothing beats reporting something unattributed.
    Not cached — see the module docstring.
    """
    root = Path(project_root)
    if not _is_main_tree(root):
        return []
    base = root / _WORKTREES_DIRNAME
    if not base.is_dir():
        return []
    out: list[tuple[str, Path]] = []
    for wt_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        log_path = wt_dir / _SHIPWRIGHT_DIR / _TRIAGE_FILE
        if not log_path.is_file():
            continue
        branch = _branch_name(wt_dir)
        if branch is None:
            continue
        out.append((branch, log_path))
    return out

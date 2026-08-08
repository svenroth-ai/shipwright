"""Trust checks for a per-session run pointer: is it OWNED by the session
being audited, and does its ``worktree_path`` name a GENUINE linked git
worktree of the main repo — not merely a directory that happens to be
contained under it and carry a `.git` entry.

Split out of ``_run_id.py`` (which had reached its 300-LOC ceiling) rather
than grown inline. Used by :func:`_run_id.pointer_worktree_root`, which
external review (round 3) found trusted a pointer's ``worktree_path`` too
readily: neither the payload's ``session_id`` (a filename alone is not proof
of ownership — two session ids can sanitise to the same name, the same gap
:func:`_run_id.pointer_run_id` already guards against) nor the worktree's
actual identity (a bare ``.exists()`` check accepts ANY directory carrying a
`.git` entry, contained under `main_root` or not the real worktree it claims
to be) was verified before redirecting the phase-quality Stop audit into it.
"""

from __future__ import annotations

from pathlib import Path


def fast_main_root(cwd: Path) -> Path | None:
    """Zero-git-process fast path for the dominant shape: ``cwd`` already IS
    the main repo root (a Stop-subprocess's cwd, even mid-iterate). Verified
    by the same ``.git``-is-a-DIRECTORY signal :func:`is_worktree_of` reads
    the opposite way — only the main checkout has that shape, a linked
    worktree never does, so this can never misidentify a worktree cwd as
    main. Avoids shelling to git (measured 30-80ms on Windows) on every one
    of the Stop hook's ~11-way plugin fan-out, run BEFORE the once-per-Stop
    claim (external review, round 3, performance). Returns any directory
    whose ``.git`` is itself a directory — a main checkout, INCLUDING a
    coincidental nested repo that happens to have one (fail-safe: the
    pointer lookup under a wrong root simply finds no pointer) — or
    ``None`` on a linked worktree or any resolution failure, in which case
    the caller falls back to the git-based resolver unchanged from before
    this optimisation (code review, delta pass — the prior wording claimed
    a nested repo returns ``None``, which the code above does not do).
    """
    try:
        resolved = cwd.resolve()
        if (resolved / ".git").is_dir():
            return resolved
    except OSError:
        pass
    return None


def pointer_owned_by_session(pointer: object, session_id: str) -> bool:
    """``True`` iff ``pointer``'s payload names ``session_id`` as its owner.

    Mirrors :func:`_run_id.pointer_run_id`'s own check verbatim: coercing via
    ``str()`` would let a non-string payload bind whenever its repr matches
    (``42`` against an audited ``"42"``), which is exactly the structural
    spoofing this exists to refuse.
    """
    if not isinstance(pointer, dict):
        return False
    payload_session = pointer.get("session_id")
    if not isinstance(payload_session, str):
        return False
    return payload_session.strip() == session_id


def is_worktree_of(worktree: Path, main_root: Path) -> bool:
    """``True`` iff ``worktree / ".git"`` is a linked-worktree gitdir FILE
    (never a directory — only the main checkout has that) whose ``gitdir:``
    line resolves under ``main_root``'s own ``.git/worktrees/`` tree.

    Both arguments must already be canonicalised (``.resolve()``d) by the
    caller. A relative ``gitdir:`` line (git >= 2.48,
    ``worktree.useRelativePaths`` / ``--relative-paths``) is resolved against
    ``worktree`` — the file that names it — not the process cwd; resolving it
    against cwd would silently fail every relative-gitdir worktree closed
    (falling through to the pre-fix main-rooted behaviour with no
    diagnostic), which round 3 also flagged.

    Two checks close the identity gap, not one (code review, D5 follow-up).
    ``relative_to(worktrees_root)`` alone accepts equality — a hand-written
    ``.git`` FILE reading ``gitdir: <main>/.git/worktrees`` (the container
    itself, always a real directory once main has ever had one worktree) or
    ``gitdir: <main>/.git/worktrees/<some-other-worktree>`` (a genuine
    ADMIN dir naming a DIFFERENT worktree) both satisfy it. ``gitdir.parent
    == worktrees_root`` rejects the container case but not the sibling-admin
    case, so the second check reads git's own back-link: every worktree
    admin dir contains a ``gitdir`` file naming the linked worktree's own
    ``.git`` file, written by git itself and not reachable through
    ``worktree_path`` alone. Only when that back-link resolves to
    ``worktree / ".git"`` is the pairing mutual, not merely one-directional.
    """
    git_entry = worktree / ".git"
    if not git_entry.is_file():
        return False
    try:
        text = git_entry.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return False
    line = text.strip()
    if not line.startswith("gitdir:"):
        return False
    raw = line[len("gitdir:"):].strip()
    gitdir = (worktree / raw).resolve()
    worktrees_root = (main_root / ".git" / "worktrees").resolve()
    if gitdir.parent != worktrees_root:
        return False
    # `.resolve()` on a non-strict path succeeds even for one that was never
    # created — a `.git` FILE naming a plausible but nonexistent gitdir would
    # otherwise pass (code review, D5 follow-up: this became the sole gate
    # once the redundant relative_to(main_root) containment pre-check was
    # dropped from the caller).
    if not gitdir.is_dir():
        return False
    try:
        back_link = (gitdir / "gitdir").read_text(encoding="utf-8", errors="strict").strip()
    except (OSError, UnicodeDecodeError):
        return False
    # Resolved against `gitdir` — the admin dir that names it — not the
    # process cwd (doubt-review delta pass): `worktree.useRelativePaths`
    # writes this back-link relative too, and `Path(back_link).resolve()`
    # alone would silently reject every such worktree. `gitdir / back_link`
    # no-ops correctly when `back_link` is absolute (pathlib: an absolute
    # right operand discards the left), mirroring how the forward
    # `gitdir:` line is already resolved against `worktree` above.
    return (gitdir / back_link).resolve() == git_entry


__all__ = ["fast_main_root", "is_worktree_of", "pointer_owned_by_session"]

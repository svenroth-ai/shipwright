"""Cheap-cost state helpers for ``mark_implementation_span.py``, split out at
the same ~300-LOC guideline this codebase splits everything else at (mirrors
``lib/phase_quality/_run_id.py`` + ``_worktree_identity.py``'s own split).

All git-free: the "done" sentinel, the per-session resolved-pointer cache, and
the two fast paths that let the hook skip git-backed pointer resolution
(``lib.phase_quality._run_id.pointer_run_id``/``pointer_worktree_root``) on
the overwhelming majority of PostToolUse calls. See the parent module's
docstring for why each guard exists (code review round 2 + 3, doubt review
round 3).
"""
from __future__ import annotations

import json
from pathlib import Path

_LOCKS_DIRNAME = Path(".shipwright") / "locks"
_DONE_GLOB = "mark_implementation_span.*.done"
_RESOLVED_CACHE_NAME = "mark_implementation_span.resolved.json"
_ROOT_HINT_MAX_HOPS = 6


def repo_root_hint(cwd: Path) -> Path:
    """Best-effort, git-free repo-root normalization for the CACHE KEY only —
    never for the authoritative write path, which always uses the git-
    validated ``worktree_root`` the real resolvers return (doubt review round
    3). Walks up from ``cwd`` looking for a directory owning both ``.git``
    and ``.shipwright`` — the shape every Shipwright checkout (main or
    worktree) has — so a cwd drift within one checkout (e.g. `cd
    plugins/x`) still hits the SAME cache/marker files instead of writing
    stray duplicates one level down. Falls back to ``cwd`` unchanged if no
    such ancestor is found within a bounded number of hops."""
    try:
        current = cwd.resolve()
    except OSError:
        return cwd
    for _ in range(_ROOT_HINT_MAX_HOPS):
        if (current / ".git").exists() and (current / ".shipwright").is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent
    return cwd.resolve() if cwd.exists() else cwd


def no_active_iterate_fast_check(root_hint: Path) -> bool:
    """``True`` when ``root_hint`` is an ordinary checkout (``.git`` is a
    DIRECTORY — never true for a linked worktree, mirroring
    ``fast_main_root``'s own signal) with no active-iterate pointer for ANY
    session — a zero-git-shellout negative fast path for the overwhelmingly
    common non-iterate case (doubt review round 3: this hook's
    ``Write|Edit|Bash`` matcher fires on every tool call for the plugin's
    whole session lifetime, not merely during an active iterate, and
    ``pointer_run_id`` shells out to git unconditionally with no fast path
    of its own). Always ``False`` inside a linked worktree — that shape is
    exactly where an iterate might genuinely be active, so it must fall
    through to the real resolvers."""
    try:
        if not (root_hint / ".git").is_dir():
            return False
        active_dir = root_hint / ".shipwright" / "iterate_active"
        return not (active_dir.is_dir() and any(active_dir.iterdir()))
    except OSError:
        return False


def done_marker_path(root: Path, run_id: str) -> Path:
    return root / _LOCKS_DIRNAME / f"mark_implementation_span.{run_id}.done"


def has_any_done_marker(root: Path) -> bool:
    """Cheap pre-resolution check (no run_id known yet): any marker under
    ``root``, regardless of which run_id wrote it. Relies on one worktree
    hosting one run at a time (B1a's create path refuses a slug/branch
    collision; a same-run resume keeps the same run_id). Doubt-review round 3
    could not find a reachable path within this codebase that re-purposes an
    existing worktree directory under a DIFFERENT run_id — if that invariant
    is ever broken elsewhere, a leftover marker from a prior run in the same
    directory would suppress capture for the new one; :func:`has_done_marker`
    below is the precise, run_id-scoped check used everywhere run_id is
    already known, which is the majority of this hook's post-resolution
    calls."""
    locks_dir = root / _LOCKS_DIRNAME
    return locks_dir.is_dir() and any(locks_dir.glob(_DONE_GLOB))


def has_done_marker(root: Path, run_id: str) -> bool:
    """Precise, run_id-scoped check — used once run_id is already known
    (from cache or a fresh resolution), so it costs nothing extra to be
    exact rather than reuse the broad pre-resolution glob."""
    return done_marker_path(root, run_id).exists()


def mark_done(worktree_root: Path, run_id: str) -> None:
    try:
        marker = done_marker_path(worktree_root, run_id)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        pass


def resolved_cache_path(root_hint: Path) -> Path:
    return root_hint / _LOCKS_DIRNAME / _RESOLVED_CACHE_NAME


def read_resolved_cache(root_hint: Path, session_id: str) -> tuple[str, Path] | None:
    """A prior successful ``pointer_run_id``/``pointer_worktree_root`` result
    for THIS session, or ``None``. Re-validated on every read — session_id
    equality (the same ownership check those resolvers themselves make) and
    worktree liveness — rather than trusted blindly: this narrows *when* the
    authoritative git-backed resolution runs, not *what* it checks, so a
    session change or a reaped worktree still falls through to the real
    resolvers below."""
    try:
        data = json.loads(resolved_cache_path(root_hint).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("session_id") != session_id:
        return None
    run_id = data.get("run_id")
    worktree_root = data.get("worktree_root")
    if not isinstance(run_id, str) or not run_id or not isinstance(worktree_root, str):
        return None
    root = Path(worktree_root)
    if not root.is_dir():
        return None
    return run_id, root


def write_resolved_cache(root_hint: Path, session_id: str, run_id: str,
                          worktree_root: Path) -> None:
    try:
        path = resolved_cache_path(root_hint)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"session_id": session_id, "run_id": run_id,
                        "worktree_root": str(worktree_root)}),
            encoding="utf-8",
        )
    except OSError:
        pass

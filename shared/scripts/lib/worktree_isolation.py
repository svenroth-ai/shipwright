"""Worktree-isolation primitives for /shipwright-iterate.

Every iterate run executes in its own git worktree + branch (unconditional
isolation — see shipwright-iterate SKILL.md "Worktree Isolation"). This module
is the single source of truth shared by the two CLIs:

- ``tools/setup_iterate_worktree.py``  — creates the worktree, rebinds the
  skill's ``{project_root}``.
- ``checks/check_iterate_isolation.py`` — the F0 / F11 leak-guard.

Keeping the git/snapshot logic here guarantees the main-tree snapshot is
*written* and *read back* by the byte-identical parser, so the leak-guard's
snapshot-and-diff attribution cannot drift between producer and consumer.
"""

from __future__ import annotations

import contextlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Wire up shared/scripts so ``lib.iterate_entry`` imports regardless of caller.
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.churn_merge import TRIAGE_LOG  # noqa: E402
from lib.events_log import EVENT_FILE  # noqa: E402
from lib.iterate_entry import sanitize_run_id_for_filename  # noqa: E402

# Low-level git primitives now live in the dependency-free leaf lib.git_base.
# Re-exported here so existing ``from lib.worktree_isolation import run_git`` /
# ``GitError`` / ``main_repo_root`` / ``is_worktree`` callers keep working, and
# used by this module's own worktree helpers. Importing them from git_base
# (instead of defining them here) broke the worktree_isolation -> events_log ->
# repo_root -> worktree_isolation import cycle (CodeQL py/cyclic-import).
from lib.git_base import (  # noqa: E402,F401
    DEFAULT_GIT_TIMEOUT,
    GitError,
    is_worktree,
    main_repo_root,
    resolve_git_dirs,
    run_git,
)


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

WORKTREES_DIRNAME = ".worktrees"
RUNS_DIRNAME = "runs"  # under .shipwright/
ACTIVE_POINTER_DIRNAME = "iterate_active"  # under .shipwright/
SNAPSHOT_FILENAME = "main_tree_snapshot.json"

FETCH_TIMEOUT = 120.0

# Working-tree paths that belong to iterate's own run scaffolding. They are
# this run's infrastructure, never a "leak" into the main tree, so the leak-
# guard must ignore them whether or not .gitignore has caught up.
_RUN_INFRA_PREFIXES = (
    f".shipwright/{RUNS_DIRNAME}/",
    f".shipwright/{RUNS_DIRNAME}",
    f".shipwright/{ACTIVE_POINTER_DIRNAME}/",
    f".shipwright/{ACTIVE_POINTER_DIRNAME}",
    f"{WORKTREES_DIRNAME}/",
    f"{WORKTREES_DIRNAME}",
)

# Tracked append-only logs (shipwright_events.jsonl + .shipwright/triage.jsonl,
# the latter since campaign 2026-06-05-track-triage-jsonl). A normal iterate writes
# these PER-TREE (worktree copy, committed via F6); the leak-guard exemption is
# defense-in-depth for legitimate MAIN-repo durable-log appends — events' legacy
# F7/F7b seal + replays, and triage's background Stop-hook / on-demand triage_add
# writes — never a branch leak. EXACT root-relative paths (+ .lock sidecars).
_MAIN_TREE_WRITE_EXEMPT = tuple(
    f + s for f in (EVENT_FILE, TRIAGE_LOG) for s in ("", ".lock")
)


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------


class IsolationError(RuntimeError):
    """A worktree-isolation precondition was violated."""


# -----------------------------------------------------------------------------
# Time + atomic IO
# -----------------------------------------------------------------------------


def _now_iso() -> str:
    """UTC timestamp in canonical ``...Z`` form."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(target: Path, data: dict) -> None:
    """Write ``data`` as pretty JSON to ``target`` durably (tmp + fsync +
    os.replace) via the shared :func:`durable_atomic_write`."""
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    durable_atomic_write(target, text)


# -----------------------------------------------------------------------------
# Worktree / main-repo detection
# -----------------------------------------------------------------------------


def current_branch(root: Path) -> str:
    """Short name of the currently checked-out branch (``HEAD`` if detached)."""
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root).stdout.strip()


def default_branch(root: Path, override: str | None = None) -> str:
    """Resolve the project's default branch.

    Order: explicit ``override`` → ``origin/HEAD`` symbolic ref → ``main``.
    """
    if override:
        return override
    try:
        ref = run_git(
            ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            cwd=root,
        ).stdout.strip()
    except GitError:
        ref = ""
    if ref.startswith("origin/"):
        return ref[len("origin/") :]
    return ref or "main"


def branch_exists(root: Path, branch: str) -> bool:
    """True if a local branch ``branch`` already exists."""
    result = run_git(
        ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=root,
        check=False,
    )
    return result.returncode == 0


def is_under_worktrees(project_root: Path, main_root: Path) -> bool:
    """True when ``project_root`` resolves under ``<main_root>/.worktrees/``."""
    wt_base = (main_root / WORKTREES_DIRNAME).resolve()
    try:
        project_root.resolve().relative_to(wt_base)
        return True
    except ValueError:
        return False


# -----------------------------------------------------------------------------
# Main-tree snapshot + leak detection
# -----------------------------------------------------------------------------


def _is_run_infra(path: str) -> bool:
    # NB: a literal "./" prefix must be stripped as a prefix, not via
    # str.lstrip("./") — lstrip takes a char SET and would eat the leading
    # "." of ".shipwright".
    norm = path.replace("\\", "/")
    if norm.startswith("./"):
        norm = norm[2:]
    return any(norm == p or norm.startswith(p) for p in _RUN_INFRA_PREFIXES)


def _porcelain_path(line: str) -> str:
    """Extract the working-tree path from one ``git status --porcelain`` line."""
    # Format: ``XY <path>`` ; renames/copies use ``XY <old> -> <new>``.
    body = line[3:] if len(line) > 3 else line
    if " -> " in body:
        body = body.split(" -> ", 1)[1]
    return body.strip()


def _scan_porcelain(out: str) -> tuple[set[str], bool]:
    """Parse ``git status --porcelain`` output.

    Returns ``(paths, saw_bare_shipwright)``. ``saw_bare_shipwright`` is True
    when git collapsed a fully-untracked ``.shipwright/`` into a single entry —
    that hides run-infra (``.shipwright/runs/`` etc.) and must be re-expanded.
    """
    paths: set[str] = set()
    saw_bare_shipwright = False
    for line in out.splitlines():
        if not line.strip():
            continue
        path = _porcelain_path(line)
        if not path:
            continue
        norm = path.replace("\\", "/")
        if norm.rstrip("/") == ".shipwright":
            saw_bare_shipwright = True
            continue
        if not _is_run_infra(norm) and norm not in _MAIN_TREE_WRITE_EXEMPT:
            paths.add(norm)
    return paths, saw_bare_shipwright


def main_tree_status_paths(main_root: Path) -> set[str]:
    """Set of working-tree paths git reports as dirty/untracked in the main repo.

    Comparison is by PATH (not status code) so a path whose status shifts
    between snapshot and check (e.g. ``??`` → ``A``) is not falsely flagged.
    Run-infrastructure paths are excluded — see ``_RUN_INFRA_PREFIXES``.

    When ``.shipwright/`` is entirely untracked (a degenerate non-Shipwright
    repo), git collapses it to one ``?? .shipwright/`` entry that would hide
    the run-infra inside it; the directory is then re-scanned with
    ``--untracked-files=all`` (scoped, so it stays cheap) so the exclusion
    can see individual files.
    """
    out = run_git(
        ["-c", "core.quotePath=false", "status", "--porcelain"],
        cwd=main_root,
    ).stdout
    paths, saw_bare_shipwright = _scan_porcelain(out)
    if saw_bare_shipwright:
        sub = run_git(
            [
                "-c", "core.quotePath=false", "status", "--porcelain",
                "--untracked-files=all", "--", ".shipwright",
            ],
            cwd=main_root,
            check=False,
        ).stdout
        expanded, _ = _scan_porcelain(sub)
        paths |= expanded
    return paths


def _run_dir(main_root: Path, run_id: str) -> Path:
    return (
        main_root
        / ".shipwright"
        / RUNS_DIRNAME
        / sanitize_run_id_for_filename(run_id)
    )


def snapshot_path(main_root: Path, run_id: str) -> Path:
    """Path to the main-tree snapshot for ``run_id`` (may not exist yet)."""
    return _run_dir(main_root, run_id) / SNAPSHOT_FILENAME


def write_snapshot(main_root: Path, run_id: str) -> Path:
    """Snapshot the main tree's dirty paths NOW. Returns the snapshot path."""
    snapshot = {
        "run_id": run_id,
        "taken_at": _now_iso(),
        "main_root": str(main_root),
        "dirty_paths": sorted(main_tree_status_paths(main_root)),
    }
    target = snapshot_path(main_root, run_id)
    _atomic_write_json(target, snapshot)
    return target


def read_snapshot(main_root: Path, run_id: str) -> dict:
    """Read back the main-tree snapshot for ``run_id``.

    Raises :class:`IsolationError` if it is missing — a run that reached the
    leak-guard without a Step-1 snapshot cannot prove isolation (fail-closed).
    """
    target = snapshot_path(main_root, run_id)
    if not target.exists():
        raise IsolationError(
            f"no main-tree snapshot for run {run_id!r} at {target} — "
            "the unconditional worktree-setup step did not run"
        )
    return json.loads(target.read_text(encoding="utf-8"))


def detect_leak(main_root: Path, run_id: str) -> tuple[bool, list[str]]:
    """Compare the current main tree against the Step-1 snapshot.

    Returns ``(clean, new_paths)``. ``clean`` is True when no working-tree path
    became dirty since the snapshot — i.e. the iterate run did not leak into
    the main tree.
    """
    baseline = set(read_snapshot(main_root, run_id).get("dirty_paths", []))
    current = main_tree_status_paths(main_root)
    new_paths = sorted(current - baseline)
    return (not new_paths, new_paths)


# -----------------------------------------------------------------------------
# Run pointer (consumed by the worktree-aware Stop hook)
# -----------------------------------------------------------------------------


def write_run_pointer(
    main_root: Path,
    *,
    run_id: str,
    slug: str,
    branch: str,
    worktree_path: Path,
    session_id: str | None,
) -> Path:
    """Write a per-session pointer so the Stop hook can finalize the worktree.

    Keyed by session id (one file per concurrent session) so two parallel
    iterate setups never race on a single pointer file.
    """
    key = session_id or run_id
    pointer = {
        "run_id": run_id,
        "slug": slug,
        "branch": branch,
        "worktree_path": str(worktree_path),
        "main_root": str(main_root),
        "session_id": session_id or "",
        "created_at": _now_iso(),
    }
    target = (
        main_root
        / ".shipwright"
        / ACTIVE_POINTER_DIRNAME
        / f"{sanitize_run_id_for_filename(key)}.json"
    )
    _atomic_write_json(target, pointer)
    return target


def read_run_pointer(main_root: Path, session_id: str) -> dict | None:
    """Read the run pointer for ``session_id`` (None if absent)."""
    target = (
        main_root
        / ".shipwright"
        / ACTIVE_POINTER_DIRNAME
        / f"{sanitize_run_id_for_filename(session_id)}.json"
    )
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def prune_stale_run_pointers(main_root: Path) -> int:
    """Delete run pointers whose worktree no longer exists. Returns the count.

    Self-healing housekeeping — Abandon removes a worktree but not the
    per-session pointer, and pointers otherwise accumulate forever. Safe to
    call opportunistically; never raises.
    """
    pointer_dir = main_root / ".shipwright" / ACTIVE_POINTER_DIRNAME
    if not pointer_dir.is_dir():
        return 0
    removed = 0
    for pointer in pointer_dir.glob("*.json"):
        try:
            data = json.loads(pointer.read_text(encoding="utf-8"))
            worktree = Path(data.get("worktree_path", ""))
        except (json.JSONDecodeError, OSError):
            continue
        if not worktree.is_dir():
            with contextlib.suppress(OSError):
                pointer.unlink()
                removed += 1
    return removed

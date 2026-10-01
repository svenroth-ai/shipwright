#!/usr/bin/env python3
"""Marker + isolation state for ``iterate_worktree_gate.py`` (split out to keep
each module under the 300-line guideline). Everything here is cheap and
import-light on purpose: the unarmed fast path walks up from cwd looking for a
marker and returns without a git process or a ``lib`` import."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

_MARKER_SUBDIR = (".shipwright", "runtime", "iterate-worktree-gate")
_MARKER_TTL_SECONDS = 24 * 3600


def _marker_path(main_root: Path, session_id: str) -> Path:
    """Collision-free filename (sanitized stem + digest of the raw id), built
    without any ``lib`` import so the unarmed fast path stays import-free."""
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", session_id)[:60] or "unknown"
    digest = hashlib.sha256(session_id.encode("utf-8", "surrogatepass")).hexdigest()[:12]
    return main_root.joinpath(*_MARKER_SUBDIR) / f"{stem}-{digest}.json"


def _read_marker(main_root: Path, session_id: str) -> dict | None:
    try:
        data = json.loads(_marker_path(main_root, session_id).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and float(data["armed_at"]) > 0 else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _is_armed(main_root: Path, session_id: str) -> bool:
    marker = _read_marker(main_root, session_id)
    return (
        marker is not None
        and not marker.get("released")
        and time.time() - float(marker["armed_at"]) < _MARKER_TTL_SECONDS
    )


def _write_marker(main_root: Path, session_id: str, marker: dict) -> None:
    path = _marker_path(main_root, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")  # atomic: a parallel reader never sees a half-written marker
    tmp.write_text(json.dumps(marker), encoding="utf-8")
    os.replace(tmp, path)


def _arm(main_root: Path, session_id: str, source: str) -> None:
    if not _is_armed(main_root, session_id):  # re-arming a live marker must not extend its TTL
        _write_marker(main_root, session_id, {"armed_at": time.time(), "source": source})


def _release(main_root: Path, session_id: str) -> None:
    marker = _read_marker(main_root, session_id) or {"armed_at": time.time()}
    _write_marker(main_root, session_id, {**marker, "released": True})


def _find_armed_root(cwd: Path, session_id: str) -> Path | None:
    """The checkout holding this session's live marker, found by walking up
    from ``cwd`` -- no git process. A worktree lives under ``<main>/.worktrees/``,
    so the walk reaches the main root from there too."""
    for candidate in (cwd, *cwd.parents):
        if _is_armed(candidate, session_id):
            return candidate
    return None


def _is_isolated(cwd: Path, session_id: str) -> bool:
    """True when this session already works in a linked worktree. Cannot tell
    (not a git repo, git missing) counts as isolated: there is nothing to
    enforce where no worktree can be made."""
    fast = _linked_worktree_by_dotgit(cwd)
    if fast:
        return True
    from lib import git_base
    from lib.phase_quality._run_id import pointer_worktree_root

    if fast is None:  # no ``.git`` found on the way up: let git decide
        try:
            if git_base.is_worktree(cwd):
                return True
        except (git_base.GitError, OSError):
            return True
    return pointer_worktree_root(cwd, session_id) is not None


def _gitdir_is_linked_worktree(dotgit: Path) -> bool:
    """A ``.git`` FILE also appears in submodules and ``--separate-git-dir``
    checkouts; only a linked worktree's gitdir carries a ``commondir`` file."""
    text = dotgit.read_text(encoding="utf-8", errors="replace").strip()
    if not text.startswith("gitdir:"):
        return False
    gitdir = Path(text[len("gitdir:"):].strip())
    if not gitdir.is_absolute():
        gitdir = dotgit.parent / gitdir
    return gitdir.parent.name == "worktrees" and (gitdir / "commondir").is_file()


def _linked_worktree_by_dotgit(cwd: Path) -> bool | None:
    """Git-free answer where the layout is unambiguous: the nearest ``.git`` up
    the tree is a FILE in a linked worktree and a directory in the main
    checkout. ``None`` when none is found (submodule layouts, bare setups)."""
    for candidate in (cwd, *cwd.parents):
        dotgit = candidate / ".git"
        try:
            if dotgit.is_file():
                # Submodules and --separate-git-dir also use a .git file; only a
                # ``gitdir: .../worktrees/<name>`` pointer is a linked worktree.
                return True if _gitdir_is_linked_worktree(dotgit) else None
            if dotgit.is_dir():
                return False
        except OSError:
            return None
    return None

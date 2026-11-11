"""Staging, absorbing and sealing of event drop files (issue 978, campaign unit S4).

A drop is committed by name, never by folder (DESIGN 4.1): the shared campaign worktree
has ONE ``wt8`` for the orchestrator and all its sub-iterates, so a folder-level add would
sweep a sibling run's files into this run's commit.

* :func:`own_drops` -- untracked drops of THIS run's key (or its unit/branch key) and THIS worktree (F6 stages these);
* :func:`wt_drops` -- every untracked drop of this worktree (``ensure_current`` ABSORBS these
  before a merge; F7b seals the main tree's);
* :func:`validate_drops` -- a drop is only committed whole: every line a record, no remainder;
* :func:`commit_drops` -- explicit-path add + path-restricted commit, index restored on failure.

All lookups are ``git ls-files --others --exclude-standard`` on the folder: an IGNORED folder
yields nothing (the drops layout is then not tracked, the committed-check does not apply).
Everything here is a no-op for a tree without a drops folder, i.e. under the legacy layout.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .events_layout import drop_key, events_layout, events_lock_path, implicit_key, worktree_id
from .events_read import DROP_NAME
from .file_lock import FileLock
from .events_log import DROPS_DIR
from .jsonl_records import read_jsonl_records

_NAME = DROP_NAME  # the one drop-name rule (events_read): staging never takes a file the integrity check would refuse


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)


def _untracked(root: Path) -> list[str]:
    if not (root / DROPS_DIR).is_dir():
        return []
    proc = _git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", DROPS_DIR + "/")
    if proc.returncode != 0:
        return []
    # top level only: readers glob the folder flat, so a file in a sub-folder is never an event file
    return sorted(p for p in proc.stdout.split("\0") if p and "/" not in p[len(DROPS_DIR) + 1:])


def wt_drops(root: Path | str, wt8: str | None = None) -> list[str]:
    """Repo-relative paths of the untracked drops written from this worktree (``wt8``)."""
    root = Path(root)
    wt8 = wt8 or worktree_id(root)
    return [p for p in _untracked(root)
            if (m := _NAME.match(p.rsplit("/", 1)[-1])) and m.group("wt8") == wt8]


def own_drops(root: Path | str, run_id: str | None = None) -> list[str]:
    """Untracked drops of this worktree whose KEY is the run's key (F6 stages exactly these)."""
    root = Path(root)
    keys = {drop_key(root, None, run_id)}
    if not (implicit := implicit_key(root)).startswith("_"):
        keys.add(implicit)  # events the run wrote WITHOUT an explicit run id: only its OWN per-unit key, never a shared branch key
    return [p for p in wt_drops(root)
            if (m := _NAME.match(p.rsplit("/", 1)[-1])) and m.group("key") in keys]


def validate_drops(root: Path | str, rels: list[str]) -> list[str]:
    """Problems that forbid committing ``rels`` as they are (empty = all whole and readable)."""
    problems = []
    for rel in rels:
        try:
            read = read_jsonl_records(Path(root) / rel)
        except OSError as exc:
            problems.append(f"{rel}: unreadable ({exc.__class__.__name__})")
            continue
        if not read.records:
            problems.append(f"{rel}: no record")
        elif read.corrupt:
            problems.append(f"{rel}: {len(read.corrupt)} unrecoverable fragment(s)")
    return problems


def commit_drops(root: Path | str, rels: list[str], message: str) -> tuple[bool, str]:
    """``git add`` + path-restricted ``git commit`` of exactly ``rels``. ``(ok, detail)``; the index is restored on failure."""
    root = Path(root)
    if not rels:
        return True, "nothing"
    add = _git(root, "add", "--", *rels)
    if add.returncode != 0:
        return False, f"add failed: {add.stderr.strip()[:300]}"
    commit = _git(root, "commit", "-m", message, "--", *rels)
    if commit.returncode == 0:
        return True, "committed"
    _git(root, "reset", "-q", "--", *rels)
    return False, f"commit failed: {commit.stderr.strip()[:300]}"


def writer_lock(root: Path | str) -> FileLock:
    """The writers' lock: list -> validate -> add -> commit must not interleave with an append (a line landing
    between ``git add`` and the commit would sit in a now-closed, tracked file and never ship)."""
    return FileLock(events_lock_path(root))


def _carries_gate_event(root: Path, rel: str) -> bool:
    """True when the file holds ANY run's ``work_completed``: shipping a gate event is its owner's F6 job."""
    try:
        records = read_jsonl_records(root / rel).records
    except OSError:
        return False
    return any(r.get("type") == "work_completed" for r in records)


def absorb_wt_drops(root: Path | str, run_id: str | None = None) -> str | None:
    """Commit the untracked drops of this worktree (``ensure_current``'s ABSORB step; ``None`` = nothing to do).

    The mirror of ``_absorb_dirty_triage_log``: a late write (after F6) must not be lost at teardown. Two limits:

    * validated first -- a torn file is never committed as permanent history;
    * a file carrying a ``work_completed`` (this run's gate event, or an abandoned / sibling run's) is NOT taken:
      shipping it is its owner's F6 job, and the F11 committed-check exists to FAIL when F6 forgot (DESIGN 10.2:
      the "unstaged drop fails" rule applies after the absorb, to gate events). Everything else late is absorbed.

    Only under the drops layout, and under the writers' lock; a torn file is left out, the valid ones are taken.
    """
    root = Path(root)
    if events_layout(root) != "drops" or not wt_drops(root):
        return None  # nothing to do: no lock file is created either
    with writer_lock(root):
        candidates = [r for r in wt_drops(root) if not _carries_gate_event(root, r)]
        bad = {p.split(":", 1)[0] for p in validate_drops(root, candidates)}
        rels = [r for r in candidates if r not in bad]
        if not rels:
            return "events-absorb-skipped-invalid" if bad else None
        ok, _ = commit_drops(root, rels, "chore(events): absorb event drops")
    return "events-absorbed" if ok else "events-absorb-commit-failed"


__all__ = ["absorb_wt_drops", "commit_drops", "own_drops", "validate_drops", "writer_lock", "wt_drops"]

#!/usr/bin/env python3
"""Carry the run's own ledger across an integrate merge (trg-ad29a709).

The sibling of ``lib/derived_snapshots.py``, and the seam between them is a difference
in KIND, not a slice for size. That module enforces an ABSENCE: eleven shared derived
views must not enter an iterate commit, so any dirty one is reset to ``HEAD``. This one
preserves a PRESENCE: ``shipwright_test_results.json`` is on that list of eleven and
does not belong there, because the run WRITES it — the F5 ledger, ``iterate_latest``,
the test totals, ``test_completeness``, ``surface_verification``, ``ci_supplychain_ack``
— and no producer can recompute it. Resetting it is not undoing a regeneration; it is
deleting the run's evidence, which it did silently in two separate sessions.

**Excluding it from the restore is only half an answer, and the other half is why this
module exists.** A run-written path kept out of the restore stays tracked-and-dirty, and
a dirty path is exactly what makes ``git merge`` refuse to start once mainline moved it
("Your local changes to the following files would be overwritten by merge", exit 2) —
so the branch cannot advance at all. Both failures are real and mutually exclusive:
restore it and the evidence dies, leave it and the pipeline stops.

Neither was reasoned about. ``main`` still TRACKS the file and its copy still moves —
one of ``main``'s twelve most recent commits on 2026-07-30 (#497) changed it, since the
commit gate inspects a single commit and a multi-commit PR can carry it past — and both
git behaviours were reproduced in a throwaway repository before this was written.

So the bytes are carried in memory instead: :func:`stash_run_written` reads them and
hands git a clean path, :func:`unstash_run_written` puts them back. ``integrate_main``
calls the second in a ``finally``, because ``git merge --abort`` is ``git reset
--merge`` and refuses on the same condition — a write-back placed before the abort
paths breaks them silently.

Neither function raises, and each returns what it could not do rather than staying
quiet about it. That is the whole lesson of the defect this closes: the cost was never
the failure, it was that the failure looked exactly like success.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.atomic_write import durable_atomic_write, durable_read_bytes
from lib.derived_snapshots import DERIVED_SNAPSHOTS, RESTORABLE_SNAPSHOTS

__all__ = ["RUN_WRITTEN_SNAPSHOTS", "stash_run_written", "unstash_run_written"]

#: The complement — snapshots a RUN writes and no producer can re-derive. Derived from
#: the sibling's two sets rather than written out, so excluding a second path there
#: cannot leave this one behind.
RUN_WRITTEN_SNAPSHOTS: frozenset[str] = DERIVED_SNAPSHOTS - RESTORABLE_SNAPSHOTS


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # Its own copy rather than the sibling's private one: reaching across for a
    # `_`-prefixed name would tie the two modules tighter than the one import above,
    # which is the whole point of the seam.
    #
    # `errors="replace"` is `integrate_main._git`'s posture, not the sibling's strict
    # one, and the difference is deliberate. This function's contract is NEVER RAISES
    # — its call site sits outside integrate's own try — so a legacy un-decodable byte
    # in git's output must degrade to U+FFFD rather than become the traceback the
    # contract exists to prevent. Nothing here is re-serialised into a tracked file,
    # which is what makes strict decoding necessary on the churn-resolver side.
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _git_bytes(project_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    """``_git`` without decoding — for content that must survive as bytes.

    ``git show :<path>`` emits file CONTENT, not a status line. Decoding it would make
    the carried ledger a decode/encode round-trip through UTF-8 with ``errors=replace``,
    which is lossy by construction on exactly the input the strict/replace argument
    above is about.
    """
    return subprocess.run(
        ["git", "-C", str(project_root), *args], capture_output=True, check=False)


def stash_run_written(project_root: Path) -> tuple[dict[str, bytes], list[str]]:
    """Take the run's own ledger off the worktree. Returns ``(bytes taken, not carried)``.

    The other half of :data:`RESTORABLE_SNAPSHOTS`. Keeping a run-written path out of
    the restore protects its CONTENT but leaves it tracked-and-dirty, and a dirty path
    is exactly what makes the following ``git merge`` refuse to start once mainline
    moved it. So the content is carried in memory instead: read the bytes, hand git a
    clean path, and let :func:`unstash_run_written` put them back once the merge no
    longer needs the worktree.

    Every dirty state that has bytes anywhere is taken, and the clean-up is chosen to
    match where they were:

    - **Tracked and dirty** (``M``, ``MM``, staged-only ``M ``) — read the worktree,
      then ``git checkout HEAD --``, which clears index AND worktree in one call so a
      staged ledger cannot ride into the merge commit either.
    - **UNTRACKED** — read it, then ``unlink``. An untracked file is not harmless here:
      one an incoming merge wants to write makes git refuse just as loudly ("The
      following untracked working tree files would be overwritten by merge"), and this
      module MANUFACTURES that state, because :func:`unstash_run_written` recreates the
      ledger untracked whenever the merge deleted the path from ``HEAD``. So the merge
      after that one would refuse. The clean-up is simply a different verb.
    - **``MD``** (staged modification, worktree deletion) — nothing is on disk, but the
      INDEX still holds the run's ledger, and :func:`restore_derived_to_head` skips this
      pair too. Read it out of the index with ``git show :<path>``.

    Only a plain deletion is passed over, and only because it has no bytes in either
    place; that one is :func:`restore_derived_to_head`'s business.

    **Never raises**, and the second return value is what that costs. The caller runs
    OUTSIDE its own ``try``, so a propagating error here is a traceback with no JSON
    out of ``ensure_current`` — the shape every other failure in ``integrate_main`` is
    shaped to avoid. And a path left behind must not be quietly indistinguishable from
    "nothing to do": it stays dirty, the merge then refuses, and the operator is left
    reading a git error about a file nothing in the flow ever mentioned.
    """
    project_root = Path(project_root)
    saved: dict[str, bytes] = {}
    not_carried: list[str] = []
    for rel in sorted(RUN_WRITTEN_SNAPSHOTS):
        status = _git(project_root, "status", "--porcelain", "--", rel)
        if status.returncode != 0:
            # Could not even ASK. That is not the same as "clean", and collapsing the
            # two would leave a dirty ledger in place under the one label this function
            # promises never to give it: silence. A failed inspection is a failed carry.
            not_carried.append(rel)
            continue
        lines = (status.stdout or "").splitlines()
        if not lines:
            continue                      # genuinely clean — nothing to carry
        # Every line, not just the first: `git rm --cached` emits the pair `D ` + `?? `,
        # and that one IS tracked. (Porcelain v1 prints untracked entries last, so the
        # first line is the tracked one whenever there is one — `pair` relies on that.)
        untracked = all(ln.startswith("??") for ln in lines)
        pair = lines[0][:2]
        try:
            # Retrying, like every other read of a file a concurrent publisher may
            # hold. A bare read_bytes() raises PermissionError (winerror 5/32) when an
            # indexer or AV has the file open on Windows, and catching that alongside
            # a real deletion would skip the path, leave it dirty, and let the merge
            # refuse — the exact failure this function exists to prevent, arriving
            # silently and mislabelled. `durable_read_bytes`, not `durable_read_text`:
            # newline translation would round-trip CRLF content back as LF.
            content = durable_read_bytes(project_root / rel)
        except FileNotFoundError:
            if pair in (" D", "D ") or untracked:
                continue                      # nothing anywhere; the restore handles it
            staged = _git_bytes(project_root, "show", f":{rel}")   # `MD` — from the index
            if staged.returncode != 0:
                not_carried.append(rel)
                continue
            content = staged.stdout
        except OSError:
            not_carried.append(rel)
            continue
        if not _clear(project_root, rel, untracked):
            # Read but not cleaned. Dropping the bytes is right — nothing was moved,
            # so there is nothing to put back — but the path is still dirty.
            not_carried.append(rel)
            continue
        saved[rel] = content
    return saved, not_carried


def _clear(project_root: Path, rel: str, untracked: bool) -> bool:
    """Hand git a clean path. ``True`` when the path is no longer dirty.

    ``checkout`` (not ``restore``) for a tracked path: it resets index AND worktree in
    one call, so a ledger a producer already STAGED is unstaged too. For an untracked
    one there is no ``HEAD`` copy to check out — the file itself IS the dirt, so
    removing it is the same operation expressed against a path git does not know.
    """
    if not untracked:
        return _git(project_root, "checkout", "HEAD", "--", rel).returncode == 0
    try:
        (project_root / rel).unlink()
    except OSError:
        return False
    return True


def unstash_run_written(
    project_root: Path, saved: dict[str, bytes]
) -> tuple[list[str], list[str]]:
    """Put back what :func:`stash_run_written` carried. Returns ``(written, failed)``.

    Called once git no longer needs the path clean — which is as soon as the merge has
    either started or refused, and deliberately BEFORE anything that can raise. The
    file goes back to dirty, which is its correct state: it is this run's evidence and
    no iterate commits it.

    If the merge DELETED the path from ``HEAD``, this recreates it as an untracked
    file. That is the intended outcome rather than an oversight — every F11 reader
    opens it by path, so an untracked ledger is still read, and the alternative is
    losing the run's evidence to a mainline change that has nothing to do with it.

    A write that fails is REPORTED, not merely omitted. It cannot raise — it runs in a
    ``finally``, where an exception would mask the result or error being returned — so
    swallowing is forced; being silent about it is not. This is the one remaining path
    on which the run's ledger can be lost, inside the feature written to end exactly
    that, so the caller gets a name for it instead of a result that reads identically
    to "there was nothing to carry".
    """
    project_root = Path(project_root)
    written: list[str] = []
    failed: list[str] = []
    for rel, content in sorted(saved.items()):
        try:
            durable_atomic_write(project_root / rel, content)
        except OSError:
            failed.append(rel)
            continue
        written.append(rel)
    return written, failed

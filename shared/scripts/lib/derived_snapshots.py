#!/usr/bin/env python3
"""The shared mutable snapshots an iterate branch must NOT carry.

Own module (not folded into ``lib/churn_merge.py`` or
``tools/resolve_churn_conflicts.py``) for two reasons: both of those carry a
bloat-baseline entry that this would ratchet, and the concern is genuinely
distinct. ``CHURN_ALLOWLIST`` says what the resolver may auto-resolve *when* a
conflict happens; :data:`DERIVED_SNAPSHOTS` says what must never enter an iterate
commit in the first place, so the conflict cannot arise.

Background (iterate-2026-07-27-derived-snapshots-off-branch). Every path here is
a pure derivation of ``shipwright_events.jsonl`` + ``.shipwright/triage.jsonl`` +
git history — all of which DO ship in the PR. Committing the *view* alongside the
truth was both:

- **conflict-generating** — every iterate rewrites the same eleven shared paths
  regardless of what it changed, so N parallel iterates collide N(N-1)/2 times on
  files carrying no information about any of the changes; and
- **wrong** — a branch-local derivation reads the *branch's* git history
  (pre-squash SHAs, integrate commits) and an event log missing every
  concurrently-merging branch. Measured on 2026-07-27, ``main``'s committed
  ``change-history.md`` over-counted commits by 11 and cited a SHA that
  ``git merge-base --is-ancestor`` proves was never on ``main``.

Deliberately EXCLUDED: the append-only logs (``merge=union`` composes them
correctly across branches) and every per-run / per-campaign path
(``.shipwright/agent_docs/iterates/<run_id>.json``, ``reviews.json``, campaign
``status.json``) — those cannot collide, so they still ship.

One of the eleven does not belong on the list and cannot simply be dropped from it:
``shipwright_test_results.json`` must stay OUT of the commit like the rest, but a run
WRITES it and nothing can re-derive it, so it is carried across the merge rather than
reset. That mechanism is ``lib/run_written_ledger.py``; this module keeps the single
job of saying what must be absent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.churn_merge import (
    CI_SECURITY_SUMMARY,
    DERIVED_MDS,
    TEST_RESULTS,
    TEST_TRACEABILITY,
    THROUGHPUT_REPORT,
    norm,
)

__all__ = ["DERIVED_SNAPSHOTS", "RESTORABLE_SNAPSHOTS", "restore_derived_to_head"]

#: The twelve paths. Derived from the churn registry so a new derived MD is picked
#: up here automatically instead of drifting into a second hand-maintained list.
DERIVED_SNAPSHOTS: frozenset[str] = DERIVED_MDS | {
    CI_SECURITY_SUMMARY,
    TEST_TRACEABILITY,
    TEST_RESULTS,
    THROUGHPUT_REPORT,
}

#: The subset :func:`restore_derived_to_head` may reset — everything a producer can
#: RE-DERIVE. ``shipwright_test_results.json`` is excluded because a run WRITES it
#: and nothing can recompute it, so it is not a derivation at all.
#:
#: **Why this exclusion exists** (trg-ad29a709): F5 writes the run's ledger —
#: ``iterate_latest``, the test totals, ``test_completeness``, ``surface_verification``,
#: ``ci_supplychain_ack`` — into that file. ``ensure_current`` then integrates ``main``
#: and calls this function, which reset the file to HEAD and silently discarded the
#: block F5 had just written. Two sessions reported it independently; one had its F5
#: block overwritten twice in a single run, and a landmine note in the operator's
#: memory had already failed to prevent a third.
#:
#: Restoring a derived path is free — the next regeneration recreates it. Restoring a
#: run-written path is pure data loss, and losing it silently is what made this cost
#: whole sessions rather than minutes.
#:
#: **The cost this carve-out would otherwise impose — measured, not reasoned about.**
#: ``integrate_main`` calls the restore BEFORE its merge precisely because a
#: tracked-and-dirty path makes ``git merge`` refuse outright ("Your local changes to
#: the following files would be overwritten by merge", exit 2) when mainline touches the
#: same path. Excluding a path from the restore leaves it dirty across that merge, so
#: the exclusion hands that refusal straight to every iterate — ``ensure_current``
#: returns exit 6 and no branch advances.
#:
#: The first draft of this carve-out argued the trigger could not fire, on the premise
#: that nothing commits ``shipwright_test_results.json`` any more. **That premise is
#: false.** ``main`` still tracks the file, and its copy still moves: of ``main``'s
#: twelve most recent commits on 2026-07-30, one (#497) changed it — the commit gate
#: inspects a single commit, so a multi-commit PR can still carry it in. Both halves
#: were then measured directly, in a throwaway repo: mainline moving the path while the
#: worktree copy is dirty aborts the merge exactly as described.
#:
#: So the durable answer is built rather than deferred, and it lives in
#: ``lib/run_written_ledger.py``: the bytes are carried across the merge instead of
#: being restored. This module is left with one job — say what must be absent — and
#: that one is the complement, its :data:`RUN_WRITTEN_SNAPSHOTS` derived from this set.
RESTORABLE_SNAPSHOTS: frozenset[str] = DERIVED_SNAPSHOTS - {TEST_RESULTS}


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # encoding="utf-8" to match the rest of the churn tooling on Windows, where
    # text=True would otherwise decode git output through the cp1252 locale.
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def restore_derived_to_head(project_root: Path) -> list[str]:
    """Restore every dirty :data:`RESTORABLE_SNAPSHOTS` path to ``HEAD`` — plus a
    run-written one whose content is already GONE (see below; a deletion loses nothing).

    An iterate no longer commits these, but producers still WRITE them during the
    run: F5a/F5b regenerate them for the run's own readers, and a merge's conflict
    resolution rewrites them. Left modified-but-unstaged they keep the worktree
    permanently dirty, which is not merely untidy — a later ``git merge`` refuses
    when a local modification overlaps an incoming change, and a stray
    ``git add -A`` would smuggle the snapshot straight back into the PR.

    UNTRACKED paths are skipped: ``git checkout HEAD --`` on a path git has never
    seen exits non-zero, so a project that simply does not keep, say,
    ``.shipwright/compliance/`` must not be dragged into a failure — and "restored"
    must not claim a file it did not touch. Returns the restored relpaths, sorted.
    Never raises — restoring is hygiene, not a gate.

    **Not** :data:`DERIVED_SNAPSHOTS`: ``shipwright_test_results.json`` is written by
    the run and cannot be re-derived, so resetting it destroys the F5 ledger rather
    than merely undoing a regeneration (trg-ad29a709 — see
    :data:`RESTORABLE_SNAPSHOTS`).

    Three things this must NOT do, all found in review:

    - **Filter on ``exists()`` for a DERIVED path.** A deleted tracked snapshot
      (a ``git rm``, or a producer that removed it) is dirty precisely because it
      is gone from disk; skipping it would let the deletion ride into the iterate
      commit — the very exclusion this function enforces. Presence on disk is not
      the question; being known to ``HEAD`` is.

      The run-written path below reads ``exists()`` deliberately, and that is the
      opposite case rather than an exception to this one. There the question IS
      about content: the status pair alone cannot tell a real deletion from a
      ``git rm --cached``, where the ledger is still sitting on disk. Derived:
      restore regardless, nothing can be lost. Run-written: restore only once the
      content is confirmed gone.
    - **Restore in one batch.** ``git checkout HEAD -- a b c`` is all-or-nothing:
      one path unknown to ``HEAD`` can abort the whole call and silently leave the
      others dirty. Restoring per path keeps one odd file from defeating the rest,
      and makes the return value honest about what actually moved.
    - **Overwrite a MODIFIED run-written path.** There is no producer to put its
      content back. A DELETED one is different and is still restored: a deletion has
      no content to lose, and letting it ride into the commit would drop a tracked
      file. So the exclusion is about content, not about the path.
    """
    project_root = Path(project_root)
    dirty = _git(project_root, "status", "--porcelain", "--", *sorted(DERIVED_SNAPSHOTS))
    if dirty.returncode != 0 or not (dirty.stdout or "").strip():
        return []
    # Porcelain v1 line: two status chars, a space, then the path. '??' marks an
    # untracked path — there is no HEAD version to restore it to. Quoted paths
    # (core.quotepath) are stripped of their surrounding quotes.
    candidates: set[str] = set()
    for line in dirty.stdout.splitlines():
        if len(line) <= 3 or not line[3:].strip() or line.startswith("??"):
            continue
        rel = norm(line[3:].strip().strip('"'))
        if rel not in DERIVED_SNAPSHOTS:
            continue
        # A run-written path is restored ONLY when its content is GONE: restoring a
        # deletion loses nothing, restoring anything else discards the run's ledger.
        # The pair is necessary but NOT sufficient — `D ` is also what `git rm --cached`
        # emits, with the file still on disk — so the content is confirmed absent too.
        #
        # This guards DIRECT callers (the F11 remedy path, and any future one). In the
        # integrate flow it is already moot: `stash_run_written` runs first and has
        # re-added the path, so the state never reaches here.
        if rel not in RESTORABLE_SNAPSHOTS:
            if line[:2] not in (" D", "D "):
                continue
            if (project_root / rel).exists():
                continue
        candidates.add(rel)
    rels = sorted(candidates)

    restored: list[str] = []
    for rel in rels:
        # Per path, and `checkout` (not `restore`): it resets index AND worktree in
        # one call, so a snapshot a producer already STAGED is unstaged too.
        if _git(project_root, "checkout", "HEAD", "--", rel).returncode == 0:
            restored.append(rel)
    return restored

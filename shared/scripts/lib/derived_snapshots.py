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
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.churn_merge import (
    CI_SECURITY_SUMMARY,
    DERIVED_MDS,
    TEST_RESULTS,
    TEST_TRACEABILITY,
    norm,
)

__all__ = ["DERIVED_SNAPSHOTS", "restore_derived_to_head"]

#: The eleven paths. Derived from the churn registry so a new derived MD is picked
#: up here automatically instead of drifting into a second hand-maintained list.
DERIVED_SNAPSHOTS: frozenset[str] = DERIVED_MDS | {
    CI_SECURITY_SUMMARY,
    TEST_TRACEABILITY,
    TEST_RESULTS,
}


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
    """Restore every dirty :data:`DERIVED_SNAPSHOTS` path to ``HEAD``.

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

    Two things this must NOT do, both found in review:

    - **Filter on ``exists()``.** A DELETED tracked snapshot (a ``git rm``, or a
      producer that removed it) is dirty precisely because it is gone from disk;
      skipping it would let the deletion ride into the iterate commit — the very
      exclusion this function enforces. Presence on disk is not the question;
      being known to ``HEAD`` is.
    - **Restore in one batch.** ``git checkout HEAD -- a b c`` is all-or-nothing:
      one path unknown to ``HEAD`` can abort the whole call and silently leave the
      others dirty. Restoring per path keeps one odd file from defeating the rest,
      and makes the return value honest about what actually moved.
    """
    project_root = Path(project_root)
    dirty = _git(project_root, "status", "--porcelain", "--", *sorted(DERIVED_SNAPSHOTS))
    if dirty.returncode != 0 or not (dirty.stdout or "").strip():
        return []
    # Porcelain v1 line: two status chars, a space, then the path. '??' marks an
    # untracked path — there is no HEAD version to restore it to. Quoted paths
    # (core.quotepath) are stripped of their surrounding quotes.
    rels = sorted({
        norm(line[3:].strip().strip('"'))
        for line in dirty.stdout.splitlines()
        if len(line) > 3 and line[3:].strip() and not line.startswith("??")
    } & DERIVED_SNAPSHOTS)

    restored: list[str] = []
    for rel in rels:
        # Per path, and `checkout` (not `restore`): it resets index AND worktree in
        # one call, so a snapshot a producer already STAGED is unstaged too.
        if _git(project_root, "checkout", "HEAD", "--", rel).returncode == 0:
            restored.append(rel)
    return restored

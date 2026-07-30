#!/usr/bin/env python3
"""Steps 5 and 6 of the integrate flow: re-project, then commit the re-projection.

Split out of ``integrate_main`` when that file crossed the 300-line source cap. The
seam is a real one rather than a budgetary slice: everything here runs **after the
merge commit has already landed**, and that changes what a failure means. Up to that
point a failure can `git merge --abort` and leave the branch exactly as it was; from
here there is nothing to abort — HEAD has advanced — so every path below reports a
structured status and leaves the merge intact. Two of the flow's eight exit codes
(``regenerate_failed``, ``followup_commit_failed``) exist only in this file.

Why a re-projection is needed at all: the merge may have resolved a campaign
``status.json`` by picking a side, which leaves the board describing neither branch's
truth. It is re-derived from the append-logs, scoped to the campaigns this merge
actually CONFLICTED on — re-deriving an untouched campaign would be destructive.

The follow-up is a **separate, non-merge commit** carrying a ``Run-ID:`` trailer, and
that is load-bearing: ``audit_staleness.find_snapshot_commit`` uses
``git log --diff-filter=AM``, which skips merge commits, so a trailer on the merge
itself is invisible to the snapshot-provenance audit.

``git`` is passed in rather than imported. ``integrate_main._git`` is the monkeypatch
target five commit-failure tests bind to, and it is what ``ensure_current`` calls, so
it stays there; importing it back would make the cycle. Taking it as an argument keeps
one implementation, keeps those patches effective, and keeps the dependency pointing
one way.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.churn_merge import is_campaign_status  # noqa: E402
from lib.derived_snapshots import (  # noqa: E402
    RESTORABLE_SNAPSHOTS,
    restore_derived_to_head,
)
from tools import resolve_churn_conflicts as rcc  # noqa: E402

__all__ = ["regenerate_after_merge"]


def regenerate_after_merge(
    project_root: Path,
    run_id: str,
    *,
    git: Callable[..., subprocess.CompletedProcess[str]],
    resolved: list[str],
    branch: str,
    session_id: str | None,
    reason: str,
    steps: list[str],
) -> dict | None:
    """Re-project and commit. ``None`` means "carry on"; a dict is a terminal result.

    The ``None``-or-result contract is deliberate and is the reason this reads as one
    function rather than two. Both outcomes are *the caller's* return value — there is
    no third thing to do with them — so folding them into one return type would only
    move the branch to the call site. ``steps`` is appended to in place, so a caller
    that returns early still reports what got done.
    """
    # Scope campaign-status regen (S3) to the campaign(s) this merge actually
    # CONFLICTED on — re-deriving an untouched campaign would be destructive.
    camp_rels = [r for r in resolved if is_campaign_status(r)]
    # only=set(): an iterate branch no longer carries the derived snapshots
    # (iterate-2026-07-27-derived-snapshots-off-branch), so re-deriving them here
    # would re-create the very diff that made parallel iterates collide. The merge
    # itself still resolves them (mainline side) — they simply match `main`
    # afterwards and stay out of the PR. Campaign statuses still ship.
    outcomes = rcc.regenerate_tracked_snapshots(
        project_root, run_id, session_id=session_id, reason=reason,
        campaign_status_rels=camp_rels, only=set(),
    )
    # The merge's conflict resolution may have left the derived paths modified but
    # unstaged (resolver picks a side, nothing commits it now). Restore them to the
    # merge commit so the worktree is CLEAN: a tracked-but-dirty path makes a later
    # `git merge` refuse when it overlaps an incoming change, and invites a stray
    # `git add -A` to smuggle the snapshot back into the PR.
    restore_derived_to_head(project_root)

    failed = [k for k, v in outcomes.items() if v == "error"]
    if failed:
        # Transactional rollback: restore every derived snapshot (the .md set AND
        # the ci-security.json summary, whose best-effort refresh may have mutated
        # it before another generator failed) AND any campaign status.json touched
        # this pass (campaign S3) to the just-made merge commit, so a partial
        # regeneration never leaves a dirty tree.
        # RESTORABLE_SNAPSHOTS, not a hand-rolled union: it is set-identical and it
        # is the ONE place that knows the run-written path is excluded, so a future
        # change to that carve-out reaches this rollback too.
        restorable = [
            p for p in sorted(RESTORABLE_SNAPSHOTS) if (project_root / p).exists()
        ]
        restorable += [
            k for k in sorted(outcomes)
            if is_campaign_status(k) and (project_root / k).exists()
        ]
        # Per path, not one batched `checkout HEAD -- a b c`. The batch is
        # all-or-nothing: a single path unknown to HEAD (a ci-security.json main never
        # tracked) aborts the call, and it runs check=False, so `regenerate_failed`
        # would be returned over a tree where NOTHING was rolled back. That is the same
        # rule `restore_derived_to_head` states for itself, and this rollback sat one
        # import away from it while doing the opposite.
        for rel in restorable:
            git(project_root, "checkout", "HEAD", "--", rel, check=False)
        return {"status": "regenerate_failed", "failed": failed, "steps": steps}

    # `git diff --cached --quiet` exits 1 when there ARE staged changes.
    if git(project_root, "diff", "--cached", "--quiet", check=False).returncode != 0:
        msg = (
            f"chore(churn): regenerate derived snapshots after {branch} merge\n\n"
            f"Run-ID: {run_id}"
        )
        # F17: the merge commit already landed (HEAD advanced, no MERGE_HEAD), so a
        # failed follow-up commit must NOT `git merge --abort` (nothing in progress)
        # — surface a structured status; the regenerated snapshots remain staged for
        # a manual retry. Never raise CalledProcessError.
        try:
            git(project_root, "commit", "-m", msg)
        except subprocess.CalledProcessError as exc:
            return {
                "status": "followup_commit_failed",
                "stderr": (exc.stderr or "").strip()[:500],
                "message": "regenerate follow-up commit refused; merge commit is intact",
                "steps": steps,
            }
        steps.append("regenerated-followup")
    else:
        # No diff: finalize's own Run-ID commit remains the audit anchor (M1).
        steps.append("regenerate-noop")
    return None

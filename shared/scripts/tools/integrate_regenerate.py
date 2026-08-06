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

from lib.adr_index import refresh_best_effort, regen_command_resolved  # noqa: E402
from lib.churn_merge import ADR_INDEX, is_campaign_status  # noqa: E402
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
        # is the ONE place that knows which run-written paths are excluded, so a
        # future change to that carve-out reaches this rollback too. It already has:
        # session_handoff.md joined the carve-out in P2.15 and is correctly skipped
        # here — nothing regenerates it on this path (`only=set()`), so there is
        # nothing to roll back, and its bytes are written back by integrate_main's
        # `finally` instead.
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

    # The ADR index — re-derived AFTER the restore (so it survives it, AC4) and after
    # the rollback return (so a `regenerate_failed` tree is never left with a staged
    # index, which would falsify the rollback's "never leaves a dirty tree" invariant).
    # It sits here rather than inside `regenerate_tracked_snapshots` because that
    # function is scoped by `only`, and the call above passes `only=set()` — anything
    # gated there would never run on the one path that matters. Re-deriving is correct
    # by construction, not a heuristic: the index is a pure function of the merged
    # folder listing, which now holds both sides' ADR files (trg-1acb5304, ADR-118).
    #
    # Fail-soft, like the register's other best-effort producer (ci-security.json:
    # "else the mainline `--theirs` placeholder stands") — the merge commit has
    # already landed, so raising here would strand it over a transient lock without
    # undoing anything. Every branch records a step AND prints to stderr — but note
    # no gate reads these tokens yet (F11 branches on `ensure_current`'s exit code,
    # and all three branches still return status "ok"), so the operator-visible
    # signal is the stderr line. The byte-exact backstop,
    # `test_committed_index_is_not_stale`, runs in CI on THIS PR — but it is a
    # monorepo test, not scaffolded into adopted repos, where stderr is all there is.
    index_warning = refresh_best_effort(project_root)
    if index_warning:
        steps.append("adr-index-refresh-failed")
        print(f"integrate_regenerate: {index_warning}", file=sys.stderr)
    elif (project_root / ADR_INDEX).exists():
        steps.append("adr-index-refreshed")
        # check=False: a raise here is exactly the stranded merge this module's
        # contract forbids (a transient index.lock, a consumer repo that gitignores
        # the path). Nothing is staged on the failure branch above by design — the
        # resolver already committed the `--theirs` side, so an add would be a no-op.
        if git(project_root, "add", "--", ADR_INDEX, check=False).returncode != 0:
            steps.append("adr-index-stage-failed")
            # Rewind rather than leave it modified-but-unstaged. Nothing else would
            # ever clean it: `restore_derived_to_head` deliberately does not cover
            # this path (AC4), so a dirty index here is dirty forever, and since
            # mainline touching the index is now the NORMAL case, the next
            # `git merge` hits "local changes would be overwritten" and blocks the
            # branch outright. Restoring is free — the file is a pure function of a
            # folder already in the merge commit.
            #
            # Best-effort in turn: the dominant trigger (a transient .git/index.lock)
            # can fail this checkout too, since it writes the same index. That is the
            # status quo, not a regression, so it gets its own step rather than a
            # promise this cannot keep.
            # The message BRANCHES on what actually happened. A fixed line here would
            # be false on the restore-failed path in both halves — the file was not
            # rewound and is not stale, it holds correct content that is merely
            # unstaged — and it would prescribe a remedy that cannot clear it
            # (regenerating rewrites the same bytes and leaves it just as dirty).
            # `integrate_merge`'s docstring already states the standard: a message
            # asserting a repository state that can simply be false was rated HIGH.
            if git(project_root, "checkout", "HEAD", "--", ADR_INDEX, check=False).returncode:
                steps.append("adr-index-restore-failed")
                print(
                    f"integrate_regenerate: could not stage {ADR_INDEX}, and could not "
                    f"rewind it either. It holds correct re-derived content but is "
                    f"MODIFIED-BUT-UNSTAGED, which will block the next merge. Clear it "
                    f"with `git add -- {ADR_INDEX}` or `git checkout HEAD -- {ADR_INDEX}`.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"integrate_regenerate: could not stage {ADR_INDEX}; it was rewound "
                    f"to the merge commit and is now STALE. Regenerate with:\n         "
                    f"{regen_command_resolved()}",
                    file=sys.stderr,
                )

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

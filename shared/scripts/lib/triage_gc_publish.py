"""What happens to main's git state after a GC compaction — the half that used to
be missing entirely.

**Audit 2026-07-28, finding 16.** ``triage_gc --apply`` rewrites the git-TRACKED
``.shipwright/triage.jsonl`` and does not commit. The rewrite removes lines, so the
working log stops being an append-only extension of HEAD, and
:func:`lib.sweep_drift.plan_main_tracked_drift` — which every iterate's worktree
setup runs — then returns ``refused: main_tracked_diverged``. The outbox sweep
reports ``skipped`` and **delivers nothing, on every subsequent iterate**, until
somebody commits the compaction. Reproduced 2026-08-06: ``no_drift`` before,
``refused`` immediately after.

Nothing told the operator. The tool printed a cheerful ``APPLIED`` report and left
the delivery channel switched off. That is what this module fixes, in two steps:

* :func:`describe_post_gc_divergence` — always, after every ``--apply``: say that
  the log is uncommitted, what it costs, and how to fix it.
* :func:`commit_compaction` — opt-in ``--commit``: do the fix. Guarded, because
  committing unprompted in the operator's main tree is the class of action
  ``reconcile_main_triage``'s guard battery exists to prevent.
"""

from __future__ import annotations

from pathlib import Path

from lib.churn_merge import TRIAGE_LOG
from lib.git_base import HOOK_GIT_TIMEOUT, TIMEOUT_RETURNCODE, run_git_soft
from lib.main_tree_guards import (
    has_staged_changes,
    is_detached,
    op_in_progress,
    path_state_vs_head,
)

#: What an operator has to know when the compaction is left uncommitted. Named as a
#: constant so the CLI, ``commit_compaction``'s refusal paths and the tests all quote
#: the same sentence — a remedy that drifts from the thing it remedies is worse than
#: none, because it is trusted.
DIVERGENCE_CONSEQUENCE = (
    "the outbox sweep will refuse `main_tracked_diverged` and deliver NOTHING on "
    "every iterate until this is committed"
)


def describe_post_gc_divergence(main_root: Path | str) -> str | None:
    """An operator-facing warning iff the tracked log may now be uncommitted.

    Speaks on ``unknown`` as well as ``dirty``: the caller only invokes this after a
    rewrite that removed lines, so "git could not tell us" is not a reason to stay
    quiet — it is a reason to say we could not confirm. Only a positive ``clean``
    buys silence. Returning ``None`` on unknown hid exactly the divergence AC-1
    exists to announce (code review).
    """
    main_root = Path(main_root)
    state = path_state_vs_head(main_root, TRIAGE_LOG)
    # `not_a_repo` is silence too: nothing tracks the log there, so no divergence and
    # no sweep to disable. Only `unknown` — git present but unable to answer — speaks.
    if state in ("clean", "not_a_repo"):
        return None
    if state == "unknown":
        return (
            f"WARNING: could not confirm whether the compaction was committed — git did not "
            f"answer for {TRIAGE_LOG}. Lines WERE removed from it, so if it is uncommitted, "
            + DIVERGENCE_CONSEQUENCE + ".\n"
            f"  Check:  git -C \"{main_root}\" status --short -- {TRIAGE_LOG}"
        )
    return (
        f"WARNING: the compaction is NOT committed. {TRIAGE_LOG} is tracked and this "
        f"rewrite REMOVED lines from it, so it is no longer an append-only extension "
        f"of HEAD — " + DIVERGENCE_CONSEQUENCE + ".\n"
        f"  Fix it now:  git -C \"{main_root}\" commit -m "
        f"\"chore(triage): compact machine-churn dismissals\" -- {TRIAGE_LOG}\n"
        f"  Or re-run this tool with --commit, which does exactly that behind the "
        f"same guards."
    )


def git_state_blocker(main_root: Path | str) -> str | None:
    """The reason main's git STATE forbids a commit, or ``None``.

    Split from :func:`commit_preflight` because only these three are re-checkable
    after the rewrite: the fourth condition (the triage path clean against HEAD) is
    true only BEFORE the compaction — afterwards the file is dirty by construction,
    which is the entire reason we are committing it. An earlier cut had
    :func:`commit_compaction` re-run the whole preflight and it refused every commit
    it was asked to make; the tests caught it immediately.
    """
    main_root = Path(main_root)
    if op_in_progress(main_root):
        return "a merge/rebase/bisect is in progress"
    if is_detached(main_root):
        return "HEAD is detached, so the commit would be unreferenced"
    if has_staged_changes(main_root):
        return "something is staged in the index"
    return None


def commit_preflight(main_root: Path | str) -> str | None:
    """The reason ``--commit`` cannot run, or ``None`` when it can.

    Evaluated by the caller BEFORE the destructive rewrite. Deciding afterwards was
    the defect a code review caught: on a detached HEAD, mid-rebase, or with anything
    staged, the tool compacted the tracked log and THEN declined to publish it,
    leaving exactly the divergence ``--commit`` exists to prevent.
    ``reconcile_main_triage`` — the precedent this module's guards were extracted
    from — checks all of these before it mutates.
    """
    main_root = Path(main_root)
    blocked = git_state_blocker(main_root)
    if blocked:
        return blocked
    state = path_state_vs_head(main_root, TRIAGE_LOG)
    if state == "dirty":
        return (f"{TRIAGE_LOG} already has uncommitted drift, so committing would fold "
                "undelivered background appends into a 'compact' commit — run "
                "reconcile_main_triage.py first")
    if state != "clean":
        return f"git could not confirm {TRIAGE_LOG} is clean ({state})"
    return None


def commit_compaction(main_root: Path | str, expected_text: str, dropped: int) -> tuple[bool, str]:
    """Commit the compaction. Returns ``(committed, message)``; never raises.

    Refuses — leaving the tree exactly as found and returning a message that still
    names :data:`DIVERGENCE_CONSEQUENCE` — when:

    * anything :func:`git_state_blocker` refuses — re-checked HERE, not merely trusted
      from the caller's earlier :func:`commit_preflight`. Two reasons. It is the
      guarded half of this module's public surface, so a future caller that forgets
      the preflight must not silently get an unguarded commit; and the CLI's call
      happens BEFORE the rewrite, with two durable writes and a full validation pass
      in between, so a HEAD that detaches in that interval would otherwise yield a
      cheerful "committed:" on a dangling commit. Read-only, idempotent probes —
      three git invocations to remove a split-responsibility trap (doubt review).
      Only the git-STATE half is re-checkable; see :func:`git_state_blocker`.
    * the file on disk is no longer the bytes GC wrote. The WebUI writer does not
      take the canonical triage lock, so it can append between the GC's release and
      here; committing then publishes content this tool never planned, under a
      subject that says "compact" (external plan review, round 2).
    """
    main_root = Path(main_root)
    blocked = git_state_blocker(main_root)
    if blocked:
        return False, f"--commit skipped: {blocked} — {DIVERGENCE_CONSEQUENCE}."
    triage_path = main_root / TRIAGE_LOG
    try:
        on_disk = triage_path.read_bytes().decode("utf-8")
    except (OSError, ValueError) as exc:
        return False, f"--commit skipped: could not re-read {TRIAGE_LOG} ({exc}) — {DIVERGENCE_CONSEQUENCE}."
    if on_disk != expected_text:
        return False, (
            f"--commit REFUSED: {TRIAGE_LOG} changed after the compaction was written "
            f"(a writer that does not take the triage lock). Committing would publish "
            f"content this run never planned. Nothing was committed — {DIVERGENCE_CONSEQUENCE}."
        )
    subject = f"chore(triage): compact {dropped} machine-churn dismissal(s)"
    # HOOK_GIT_TIMEOUT, not the 15 s default: this commit fires the bloat pre-commit
    # hook, whose cold `uv run` routinely exceeds it — and run_git KILLS on timeout,
    # which in the MAIN tree strands .git/index.lock in the operator's own repo.
    commit = run_git_soft(["commit", "-m", subject, "--", TRIAGE_LOG],
                          cwd=main_root, timeout=HOOK_GIT_TIMEOUT)
    if commit.returncode == TIMEOUT_RETURNCODE:
        return False, (
            f"--commit timed out and was killed, so whether it landed is unknown; if it "
            f"did not, {DIVERGENCE_CONSEQUENCE}. Check `git status` and `git log -1` "
            f"(and for a stranded .git/index.lock)."
        )
    if commit.returncode != 0:
        return False, f"--commit failed: {commit.stderr.strip()[:300]} — {DIVERGENCE_CONSEQUENCE}."
    return True, f"committed: {subject}"

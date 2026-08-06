#!/usr/bin/env python3
"""Integrate ``origin/main`` into an iterate branch with automatic churn-conflict
reconciliation — the single command an iterate runs to refresh a stale branch.

Flow (see iterate-2026-05-31-churn-merge-resolver, AC-6/AC-7):

  1. ``git fetch origin`` (unless ``SHIPWRIGHT_ITERATE_NO_FETCH=1`` / ``--no-fetch``)
  2. ``git merge <merge_ref>`` (default ``origin/<default-branch>``)
  3. on conflict → ``resolve_churn_conflicts.complete_merge`` (allowlist-gated;
     aborts via ``git merge --abort`` if any non-churn conflict exists)
  4. commit the merge
  5. re-project the campaign ``status.json`` boards this merge touched, and
     restore every derived snapshot to HEAD so the worktree stays clean
  6. commit any re-projection as a **separate, non-merge follow-up commit**
     carrying a ``Run-ID:`` trailer — because
     ``audit_staleness.find_snapshot_commit`` uses ``git log --diff-filter=AM``
     which skips merge commits, so the trailer MUST sit on a regular commit for
     the snapshot-provenance audit to find it.

Since iterate-2026-07-27-derived-snapshots-off-branch step 5 no longer REGENERATES
the derived snapshots: an iterate branch does not carry them (see
``lib/derived_snapshots.py``), so re-deriving here would re-create the very diff
that made parallel iterates collide. Consequence to keep in view:
``find_snapshot_commit`` will no longer find an iterate-authored snapshot commit,
so the Group-E staleness audit reports main's snapshots as increasingly stale —
which is TRUE while they are frozen, and is resolved by the post-merge refresh
producer, not by silencing the audit.

**Three files, split on what a failure is allowed to do.** This one owns the brackets:
resolving the ref, and carrying the run's own ledger across the merge (``lib/
run_written_ledger.py``) so neither the merge nor its abort trips over it. Steps 2-4
live in ``tools/integrate_merge.py``, the window where nothing has landed and every bad
outcome ends in a verified ``git merge --abort``. Steps 5-6 live in
``tools/integrate_regenerate.py``, after the merge commit, where there is nothing left
to abort and a failure can only report itself.

Devs should run THIS, never a bare ``git merge origin/main``, so the resolver is
never skipped (folds external-review O14).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.derived_snapshots import restore_derived_to_head  # noqa: E402
from lib.run_written_ledger import (  # noqa: E402
    BEST_EFFORT_CARRY,
    stash_run_written,
    unstash_run_written,
)
from tools.integrate_merge import merge_and_reconcile  # noqa: E402


def _git(project_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # encoding="utf-8": the default text=True decodes via the Windows cp1252
    # locale, mojibaking or crashing on UTF-8 git output (WP6/F22). errors="replace"
    # is correct HERE (decode-only) — integrate_main consumes git stdout for
    # status/reporting and NEVER re-serialises it back into a tracked file, so a
    # legacy un-decodable byte should degrade to U+FFFD rather than crash the
    # JSON contract (vs resolve_churn._git, which is strict to keep the union
    # round-trip byte-identical). Inline (no shared helper) to stay independent
    # of the parallel WP7/WP8 subs.
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def _default_branch(project_root: Path) -> str:
    """Resolve origin's default branch (``origin/HEAD`` → name), fallback ``main``."""
    proc = _git(project_root, "rev-parse", "--abbrev-ref", "origin/HEAD", check=False)
    ref = proc.stdout.strip()
    if proc.returncode == 0 and ref.startswith("origin/"):
        return ref[len("origin/"):]
    return "main"


def integrate(
    project_root: Path,
    run_id: str,
    *,
    merge_ref: str | None = None,
    default_branch: str | None = None,
    session_id: str | None = None,
    reason: str = "merge origin/main reconciliation",
    do_fetch: bool = True,
    regenerate: bool = True,
) -> dict:
    """Run the integrate flow. Returns a structured result dict (also the CLI's
    JSON). ``merge_ref`` overrides the merge source (default ``origin/<default>``);
    used by tests to merge a local branch without a remote."""
    project_root = Path(project_root).resolve()
    steps: list[str] = []

    # NB (campaign 2026-06-08-triage-outbox-delivery / D2, Codex Q1): the merge
    # below runs in THIS worktree, never against the main tree, and with D1+D2
    # the main tracked triage.jsonl no longer accrues background drift (idle-main
    # producers route to the gitignored outbox, swept into the iterate branch at
    # worktree setup). The old reconcile_main_triage(project_root) call here was
    # therefore vestigial AND the chief generator of the local-main fold-commit
    # pile-up — so it is intentionally NOT called. The manual fallback remains at
    # tools/reconcile_main_triage.py for a hand pull with no imminent iterate.

    if do_fetch and os.environ.get("SHIPWRIGHT_ITERATE_NO_FETCH") != "1":
        fetched = _git(project_root, "fetch", "origin", check=False)
        steps.append("fetched" if fetched.returncode == 0 else "fetch-failed")

    branch = default_branch or _default_branch(project_root)
    ref = merge_ref or f"origin/{branch}"
    if _git(project_root, "rev-parse", "--verify", "--quiet", ref, check=False).returncode != 0:
        return {"status": "bad_ref", "ref": ref, "steps": steps}

    # BEFORE the merge, not after. F5a/F5b regenerate the derived snapshots for the
    # run's own readers and F6 no longer commits them, so they sit tracked-and-dirty
    # — and `git merge` REFUSES outright ("local changes would be overwritten") the
    # moment mainline touches the same path, which is the normal case since every
    # other iterate rewrites them too. Verified: with the restore placed after the
    # merge, integrate returned `merge_failed` and the branch could not advance.
    # ...and the run's OWN ledger is carried in memory across it rather than restored,
    # because no producer can put its content back (trg-ad29a709). Both halves serve
    # the same merge: the path has to be clean, and the bytes have to survive.
    stashed, not_carried = stash_run_written(project_root)
    # The `try` opens HERE, one line after the stash, and not at the merge below. Once
    # the stash has run, `stashed` is the ONLY copy of the run's evidence — the path on
    # disk is back at HEAD — so every statement after it must be covered or a traceback
    # in between takes the ledger with it. `restore_derived_to_head` is documented not
    # to raise, but "documented" is not the same as "guaranteed by this function", and
    # this is the one window the whole feature exists to close.
    #
    # A `finally`, and the first draft was wrong to avoid one. The argument for a single
    # site after the merge command was that git needs the path clean only for the merge
    # to START. It needs it clean to ABORT as well: `git merge --abort` is
    # `git reset --merge`, which refuses when a path differing between HEAD and the
    # index has unstaged changes — exactly the state the write-back creates in the case
    # this feature exists for (mainline moved the path, so the index differs). Measured,
    # not deduced: `error: Entry '<path>' not uptodate. Cannot merge.`, exit 128,
    # MERGE_HEAD left standing. `merge_and_reconcile` aborts on three paths, all inside
    # this try, so the write-back is strictly after every one of them.
    #
    # `steps` is appended to AFTER a `return` has built its dict, which still shows up:
    # the dict holds a reference to this same list, not a copy.
    outcome: dict | None = None
    try:
        if not_carried:
            # Could not be taken, so it stays dirty and the merge below may refuse.
            # Named here because the merge error would otherwise be about a file
            # nothing in this flow had mentioned.
            steps.append("ledger-not-carried")
            # ...except for a BEST_EFFORT_CARRY path, where staying dirty is the worse
            # outcome of the two. Before P2.15 the restore below cleaned the handoff
            # unconditionally; carving it out of the restore is what made "uncarried"
            # able to block the merge at all, so the carve-out brings its own fallback
            # rather than importing a new pipeline-stopping mode for a warning-severity
            # artifact (Stage-3 doubt review, medium). check=False: a reset that fails
            # leaves exactly the state the step above already reported.
            #
            # The reset itself can fail, and often for the very reason the carry did —
            # a lost `index.lock`, an unreadable path. The merge is still ATTEMPTED
            # rather than refused pre-emptively: it only refuses when mainline also
            # moved the path, so stopping here would turn a possible failure into a
            # certain one, and `merge_failed` is already a clean abort carrying git's
            # own message naming the file. What was missing is that the fallback could
            # silently not happen (external code review, openai/medium) — so the failed
            # reset gets its OWN step, and a later `merge_failed` is attributable
            # instead of arriving from a file nothing in this flow had mentioned.
            for rel in sorted(set(not_carried) & BEST_EFFORT_CARRY):
                reset = _git(project_root, "checkout", "HEAD", "--", rel, check=False)
                steps.append("uncarried-reset" if reset.returncode == 0
                             else "uncarried-reset-failed")
        if restore_derived_to_head(project_root):
            steps.append("restored-derived")
        outcome = merge_and_reconcile(
            project_root, run_id, git=_git, ref=ref, branch=branch,
            session_id=session_id, reason=reason, regenerate=regenerate, steps=steps,
        )
    finally:
        preserved, writeback_failed = unstash_run_written(project_root, stashed)
        if preserved:
            steps.append("ledger-preserved")
        if writeback_failed:
            steps.append("ledger-writeback-failed")
        # Split by what the loss COSTS, not by the fact of it. A best-effort member is
        # reported and survived; only a path whose content is genuinely unrecoverable
        # makes this terminal below.
        blocking_writeback = [p for p in writeback_failed if p not in BEST_EFFORT_CARRY]
        if writeback_failed and not blocking_writeback:
            steps.append("writeback-degraded")

    # AFTER the try/finally, not inside it. An earlier draft returned from the `finally`
    # — which does override the pending return, but also SWALLOWS a propagating
    # exception, so it needed an `sys.exc_info()` guard to stay honest and CodeQL
    # flagged the shape regardless. Holding the result in `outcome` says the same thing
    # without the trap: an exception simply skips everything below.
    if blocking_writeback:
        # The run's ledger is GONE and the path now holds HEAD's copy — another run's
        # block, clean, in this run's worktree. A step alone does not carry that:
        # `ensure_current` derives its verdict from `status` and F11 gates on the exit
        # code, so `ok` here would report success over the exact loss this module exists
        # to prevent.
        #
        # `blocking_writeback`, not `writeback_failed`: a BEST_EFFORT_CARRY path that
        # failed to write back has already been reported as a step, and stopping the
        # branch for it would trade a warning for a halt — with a message that names the
        # wrong producer besides ("re-run F5" cannot restore a note F5b writes).
        return {
            "status": "ledger_writeback_failed",
            "failed": blocking_writeback,
            "message": ("the merge itself is intact, but this run's ledger could not "
                        "be written back and the worktree now holds HEAD's copy — "
                        "re-run F5 before F11 reads it"),
            "steps": steps,
        }
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Integrate origin/main with churn reconciliation")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--merge-ref", default=None, help="override merge source (default origin/<default>)")
    parser.add_argument("--default-branch", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--reason", default="merge origin/main reconciliation")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--no-regenerate", action="store_true")
    args = parser.parse_args(argv)

    result = integrate(
        Path(args.project_root),
        args.run_id,
        merge_ref=args.merge_ref,
        default_branch=args.default_branch,
        session_id=args.session_id,
        reason=args.reason,
        do_fetch=not args.no_fetch,
        regenerate=not args.no_regenerate,
    )
    print(json.dumps(result, indent=2))
    status = result["status"]
    if status == "ok":
        return 0
    # Checked BEFORE the per-status ladder. `_abort_incomplete` means the branch is
    # NOT where it started, which is the opposite of what each base status promises —
    # `blocked` says "aborted; resolve by hand", and exit 2 would send the operator on
    # believing it. One code for "the repo is mid-merge", whatever led there.
    if status.endswith("_abort_incomplete"):
        print(f"ABORT: {status}: {result.get('message')}", file=sys.stderr)
        return 7
    if status == "ledger_writeback_failed":
        print(f"ABORT: {result.get('message')}: {result.get('failed')}", file=sys.stderr)
        return 9
    if result["status"] == "blocked":
        print("ABORT: non-churn conflicts — resolve by hand: " f"{result.get('blocking')}", file=sys.stderr)
        return 2
    if result["status"] in ("events_invalid", "triage_invalid"):
        print(f"ABORT: {result['status']} after merge: {result.get('errors')}", file=sys.stderr)
        return 4
    if result["status"] == "bad_ref":
        print(f"ABORT: merge ref does not resolve: {result.get('ref')}", file=sys.stderr)
        return 5
    if result["status"] == "merge_failed":
        print(f"ABORT: git merge refused: {result.get('stderr')}", file=sys.stderr)
        return 6
    if result["status"] == "merge_commit_failed":
        print(f"ABORT: {result['status']}: {result.get('message')}: {result.get('stderr')}", file=sys.stderr)
        return 7
    if result["status"] == "followup_commit_failed":
        print(f"ABORT: regenerate follow-up commit refused (merge intact): {result.get('stderr')}", file=sys.stderr)
        return 8
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

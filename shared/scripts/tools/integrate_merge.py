#!/usr/bin/env python3
"""Steps 2 to 4 of the integrate flow: merge, reconcile the churn, commit it.

The middle of a three-way split that follows the flow's own failure semantics rather
than file size. ``integrate_main`` owns what brackets the merge — resolving the ref and
carrying the run's ledger across it. This module owns the window in which **a failure
can still be undone**: nothing here has landed yet, so every bad outcome ends in
``git merge --abort`` and a branch that is exactly where it started.
``integrate_regenerate`` owns what comes after the merge commit, where there is nothing
left to abort. Two files, two different things a failure is allowed to do.

**An abort is verified, never assumed.** ``git merge --abort`` is ``git reset --merge``
and it is genuinely fallible — an ``index.lock``, a hook side effect, or a path that
differs between ``HEAD`` and the index while carrying unstaged changes (measured:
``error: Entry '<path>' not uptodate``, exit 128). It runs ``check=False``, so an
unverified call plus a message saying "merge aborted" is a claim about the repository
that can simply be false, and external review rated that HIGH on the one path that had
it. Every abort here therefore goes through :func:`_abort`, which re-reads
``MERGE_HEAD`` and reports a wedged tree as wedged.

``git`` is passed in rather than imported: ``integrate_main._git`` is what
``ensure_current`` calls and what five commit-failure tests monkeypatch, so it stays
there, and importing it back would close a cycle.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from tools import resolve_churn_conflicts as rcc  # noqa: E402
from tools.integrate_regenerate import regenerate_after_merge  # noqa: E402

__all__ = ["merge_and_reconcile"]

_Git = Callable[..., subprocess.CompletedProcess[str]]


def _abort(git: _Git, project_root: Path) -> bool:
    """``git merge --abort``, then CHECK. ``True`` when the tree is really clear.

    Split out so no caller can forget the second half. The abort is best-effort by
    necessity (``check=False`` — a raise here would replace a structured status with a
    traceback), and that is exactly why its outcome has to be read back rather than
    assumed: the whole point of returning ``blocked`` is to promise the operator an
    untouched branch, and a promise nobody verified is the defect, not the abort.
    """
    git(project_root, "merge", "--abort", check=False)
    return git(project_root, "rev-parse", "--verify", "--quiet",
               "MERGE_HEAD", check=False).returncode != 0


def _wedged(status: str, cause: str, steps: list[str], **extra) -> dict:
    """The result shape for "we tried to abort and the repo is still mid-merge".

    ``status`` is the machine token the CLI's exit-code ladder reads and is suffixed
    verbatim; ``cause`` is the human half. Kept as two arguments because deriving one
    from the other is what silently renames a status a caller matches on.
    """
    steps.append("abort-incomplete")
    return {
        "status": f"{status}_abort_incomplete",
        "message": (f"{cause}, AND `git merge --abort` failed — the repo is still "
                    "mid-merge, so this branch is NOT where it started; resolve by hand"),
        "steps": steps,
        **extra,
    }


def merge_and_reconcile(
    project_root: Path,
    run_id: str,
    *,
    git: _Git,
    ref: str,
    branch: str,
    session_id: str | None,
    reason: str,
    regenerate: bool,
    steps: list[str],
) -> dict:
    """Merge ``ref``, reconcile churn, commit. Returns the caller's result dict.

    ``steps`` is appended to in place, so a caller that returns early still reports
    what got done.
    """
    # --no-ff + --no-commit:
    #   --no-ff  → always create a real merge commit (never fast-forward), so the
    #     reachability of Run-ID-trailer commits is preserved (2026-05-27 AC-6
    #     "merge, not rebase") AND `merge_in_progress` is deterministic regardless
    #     of the runner's `merge.ff` config.
    #   --no-commit → commit nothing until churn is reconciled AND events are
    #     validated — even on a clean merge where `merge=union` silently resolves
    #     events.jsonl (the designed common case).
    merge = git(project_root, "merge", "--no-ff", "--no-commit", "--no-edit", ref, check=False)
    merge_in_progress = (
        git(project_root, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).returncode == 0
    )
    if not merge_in_progress:
        if merge.returncode != 0:
            # Merge refused before it began (e.g. unborn ref, local changes) —
            # surface it instead of silently claiming success.
            return {"status": "merge_failed", "stderr": (merge.stderr or "").strip()[:500], "steps": steps}
        # `ref` is already an ancestor — genuinely nothing to integrate.
        steps.append("already-up-to-date")
        return {"status": "ok", "steps": steps}

    # A merge is staged-but-uncommitted. complete_merge() reconciles churn conflicts
    # (if any) AND validates/dedups events.jsonl UNCONDITIONALLY (clean or conflicted).
    result = rcc.complete_merge(project_root, run_id=run_id)
    if result.status == "blocked":
        if not _abort(git, project_root):
            return _wedged("blocked", "non-churn conflicts", steps, blocking=result.blocking)
        return {"status": "blocked", "blocking": result.blocking,
                "message": "non-churn conflicts — merge aborted; resolve by hand", "steps": steps}
    if result.status in ("events_invalid", "triage_invalid"):
        if not _abort(git, project_root):
            return _wedged(result.status, f"the merge produced {result.status}", steps, errors=result.errors)
        return {"status": result.status, "errors": result.errors, "steps": steps}
    # F17: a check=True commit that fails (e.g. the pre-commit anti-ratchet hook
    # rejecting upstream growth of a baselined file) would otherwise raise
    # CalledProcessError — a traceback with no JSON, leaving the repo wedged in
    # MERGE_HEAD. Mirror every other failure path: structured status + abort.
    try:
        git(project_root, "commit", "--no-edit")
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()[:500]
        if not _abort(git, project_root):
            return _wedged("merge_commit_failed", "merge commit refused (e.g. pre-commit hook)", steps, stderr=stderr)
        return {
            "status": "merge_commit_failed",
            "stderr": stderr,
            "message": "merge commit refused (e.g. pre-commit hook) — merge aborted",
            "steps": steps,
        }
    steps.append("merge-committed")

    if regenerate:
        # Steps 5 and 6 live in their own module because the merge commit has now
        # LANDED: from here nothing can be aborted, so those paths report a status
        # and leave the merge intact.
        early = regenerate_after_merge(
            project_root, run_id, git=git, resolved=result.resolved, branch=branch,
            session_id=session_id, reason=reason, steps=steps,
        )
        if early is not None:
            return early

    return {"status": "ok", "steps": steps}

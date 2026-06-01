#!/usr/bin/env python3
"""Integrate ``origin/main`` into an iterate branch with automatic churn-conflict
reconciliation — the single command an iterate runs to refresh a stale branch.

Flow (see iterate-2026-05-31-churn-merge-resolver, AC-6/AC-7):

  1. ``git fetch origin`` (unless ``SHIPWRIGHT_ITERATE_NO_FETCH=1`` / ``--no-fetch``)
  2. ``git merge <merge_ref>`` (default ``origin/<default-branch>``)
  3. on conflict → ``resolve_churn_conflicts.complete_merge`` (allowlist-gated;
     aborts via ``git merge --abort`` if any non-churn conflict exists)
  4. commit the merge
  5. regenerate the derived MD snapshots from the merged tree
  6. commit them as a **separate, non-merge follow-up commit** carrying a
     ``Run-ID:`` trailer — because ``audit_staleness.find_snapshot_commit`` uses
     ``git log --diff-filter=AM`` which skips merge commits, so the trailer MUST
     sit on a regular commit for the snapshot-provenance audit to find it.

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

from lib.churn_merge import DERIVED_MDS  # noqa: E402
from tools import resolve_churn_conflicts as rcc  # noqa: E402


def _git(project_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def _default_branch(project_root: Path) -> str:
    """Resolve origin's default branch (``origin/HEAD`` → name), fallback ``main``."""
    proc = _git(project_root, "rev-parse", "--abbrev-ref", "origin/HEAD", check=False)
    ref = proc.stdout.strip()
    if proc.returncode == 0 and ref.startswith("origin/"):
        return ref[len("origin/"):]
    return "main"


def _has_staged_changes(project_root: Path) -> bool:
    # `git diff --cached --quiet` exits 1 when there ARE staged changes.
    return _git(project_root, "diff", "--cached", "--quiet", check=False).returncode != 0


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

    if do_fetch and os.environ.get("SHIPWRIGHT_ITERATE_NO_FETCH") != "1":
        fetched = _git(project_root, "fetch", "origin", check=False)
        steps.append("fetched" if fetched.returncode == 0 else "fetch-failed")

    branch = default_branch or _default_branch(project_root)
    ref = merge_ref or f"origin/{branch}"
    if _git(project_root, "rev-parse", "--verify", "--quiet", ref, check=False).returncode != 0:
        return {"status": "bad_ref", "ref": ref, "steps": steps}

    # --no-ff + --no-commit:
    #   --no-ff  → always create a real merge commit (never fast-forward), so the
    #     reachability of Run-ID-trailer commits is preserved (2026-05-27 AC-6
    #     "merge, not rebase") AND `merge_in_progress` is deterministic regardless
    #     of the runner's `merge.ff` config.
    #   --no-commit → commit nothing until churn is reconciled AND events are
    #     validated — even on a clean merge where `merge=union` silently resolves
    #     events.jsonl (the designed common case).
    merge = _git(project_root, "merge", "--no-ff", "--no-commit", "--no-edit", ref, check=False)
    merge_in_progress = (
        _git(project_root, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).returncode == 0
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
        _git(project_root, "merge", "--abort", check=False)
        return {"status": "blocked", "blocking": result.blocking,
                "message": "non-churn conflicts — merge aborted; resolve by hand", "steps": steps}
    if result.status == "events_invalid":
        _git(project_root, "merge", "--abort", check=False)
        return {"status": "events_invalid", "errors": result.errors, "steps": steps}
    _git(project_root, "commit", "--no-edit")
    steps.append("merge-committed")

    if regenerate:
        outcomes = rcc.regenerate_tracked_snapshots(
            project_root, run_id, session_id=session_id, reason=reason
        )
        failed = [k for k, v in outcomes.items() if v == "error"]
        if failed:
            # Transactional rollback: restore every derived MD to the just-made merge
            # commit so a partial regeneration never leaves a dirty tree.
            restorable = [p for p in sorted(DERIVED_MDS) if (project_root / p).exists()]
            if restorable:
                _git(project_root, "checkout", "HEAD", "--", *restorable, check=False)
            return {"status": "regenerate_failed", "failed": failed, "steps": steps}
        if _has_staged_changes(project_root):
            msg = (
                f"chore(churn): regenerate derived snapshots after {branch} merge\n\n"
                f"Run-ID: {run_id}"
            )
            _git(project_root, "commit", "-m", msg)
            steps.append("regenerated-followup")
        else:
            # No diff: finalize's own Run-ID commit remains the audit anchor (M1).
            steps.append("regenerate-noop")

    return {"status": "ok", "steps": steps}


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
    if result["status"] == "ok":
        return 0
    if result["status"] == "blocked":
        print("ABORT: non-churn conflicts — resolve by hand: " f"{result.get('blocking')}", file=sys.stderr)
        return 2
    if result["status"] == "events_invalid":
        return 4
    if result["status"] == "bad_ref":
        print(f"ABORT: merge ref does not resolve: {result.get('ref')}", file=sys.stderr)
        return 5
    if result["status"] == "merge_failed":
        print(f"ABORT: git merge refused: {result.get('stderr')}", file=sys.stderr)
        return 6
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

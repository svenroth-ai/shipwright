#!/usr/bin/env python3
"""Compact the triage backlog by dropping pure machine-churn dismissals.

Sub-iterate B of campaign ``2026-06-05-track-triage-jsonl`` — a maintenance tool
for the git-tracked ``.shipwright/triage.jsonl``.

The engine (policy vocabulary, plan, apply, post-rewrite validation) lives in
:mod:`lib.triage_gc_core`, and what happens to main's git state afterwards in
:mod:`lib.triage_gc_publish`; both were extracted so this file has room for the
warning below. Every name is re-exported here, so ``import triage_gc`` and
``from tools import triage_gc`` are unchanged.

Policy (decided 2026-06-05): **machine-churn ONLY** — see
:mod:`lib.triage_gc_core` for the rule and why human dismissals are kept.

"Dropping" an item means rewriting an append-only log without that item's lines —
a destructive compaction. Therefore:

- **dry-run is the default**; ``--apply`` is required to rewrite.
- ``--apply`` writes a ``.bak`` backup first and re-validates the result
  (header intact, no orphan ``status`` events, no droppable item survives).
- ``--apply`` **always** reports whether it left the tracked log uncommitted, and
  ``--commit`` folds the compaction into a ``chore(triage)`` commit. Without that,
  the rewrite silently disables the outbox delivery channel for every subsequent
  iterate (audit 2026-07-28, finding 16).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Make lib/ + the triage store importable whether invoked from the repo root or
# elsewhere (mirrors the audit_detector lazy-import shim).
_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.worktree_isolation import GitError, main_repo_root  # noqa: E402
# Re-export surface: the engine moved to lib/triage_gc_core.py and the git-state
# half to lib/triage_gc_publish.py (extracted to keep this CLI under the 300-LOC
# guideline). Historical importers — shared/tests/test_triage_gc.py,
# test_accepted_risk_convergence.py, alert_convergence's registry note — resolve
# these names from THIS module and must keep doing so.
from lib.triage_gc_core import (  # noqa: E402,F401
    MACHINE_DISMISSERS,
    MACHINE_REASONS,
    GcApply,
    _resolve_tracked_only,
    _union_droppable_ids,
    _validate_after,
    apply_gc,
    apply_gc_reporting,
    is_machine_churn,
    plan_gc,
)
from lib.triage_gc_publish import (  # noqa: E402,F401
    DIVERGENCE_CONSEQUENCE,
    commit_compaction,
    commit_preflight,
    describe_post_gc_divergence,
)


def _main_root_or(root: Path) -> Path:
    """The MAIN repo root for ``root``, or ``root`` itself when it is not a git repo.

    Not a hard failure: the GC engine works on any directory holding a triage store,
    and only the git-state half needs a repo. Falling back keeps a non-git run working
    exactly as before while a worktree run stops committing to the iterate branch."""
    try:
        return main_repo_root(root)
    except (GitError, OSError, subprocess.TimeoutExpired):
        return root


def _safe(value: object) -> str:
    """Console-encoding-safe string — triage titles/reasons can carry
    chars (e.g. ``→``) the Windows cp1252 console cannot encode, which
    would otherwise crash the report mid-print.
    """
    enc = sys.stdout.encoding or "utf-8"
    return str(value).encode(enc, errors="replace").decode(enc)


def _print_report(plan: dict, *, applied: bool) -> None:
    dropped = plan["dropped"]
    header = "APPLIED" if applied else "DRY-RUN (no changes written)"
    print(f"triage_gc [{header}]")
    print(f"  total items:   {plan['total']}")
    print(f"  droppable:     {len(dropped)} (machine-churn dismissals)")
    print(f"  kept:          {plan['kept_count']}")
    if dropped:
        from collections import Counter
        by_reason = Counter(i.get("statusReason") for i in dropped)
        print("  by reason:")
        for reason, n in sorted(by_reason.items(), key=lambda kv: -kv[1]):
            print(f"    {n:>4}  {_safe(reason)}")
        print("  ids (first 40):")
        for i in dropped[:40]:
            print(f"    {i['id']}  {_safe(i.get('statusBy')):<14} {_safe((i.get('title') or ''))[:48]}")
        if len(dropped) > 40:
            print(f"    ... +{len(dropped) - 40} more")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root", required=True, type=Path)
    ap.add_argument(
        "--apply", action="store_true",
        help="rewrite the log (default: dry-run report only)",
    )
    ap.add_argument(
        "--no-backup", action="store_true",
        help="skip the .bak backup on --apply (NOT recommended)",
    )
    ap.add_argument(
        "--commit", action="store_true",
        help="with --apply: also commit the compaction, so the outbox sweep keeps "
             "working. Refuses if the triage log already carried uncommitted drift.",
    )
    args = ap.parse_args(argv)
    if args.commit and not args.apply:
        ap.error("--commit requires --apply (there is nothing to commit without a rewrite)")

    plan = plan_gc(args.project_root)
    if not args.apply:
        _print_report(plan, applied=False)
        return 0
    if not plan["drop_ids"]:
        _print_report(plan, applied=False)
        print("triage_gc: nothing to drop — no rewrite performed.")
        return 0

    if args.commit:
        # `--commit` is MAIN-TREE ONLY. The store half compacts whatever root it is
        # pointed at, but committing that file from inside an iterate worktree would
        # put a `chore(triage): compact ...` commit on somebody's feature branch. The
        # first attempt at this resolved the main root for the git half and kept the
        # store on --project-root, which is incoherent: it compacted one file and
        # then compared the OTHER against it. Refuse instead (code review).
        resolved = args.project_root.resolve()
        if _main_root_or(args.project_root).resolve() != resolved:
            print(f"triage_gc: --commit refused, nothing was rewritten — {resolved} is not the "
                  "main repo root (a compaction commit here would land on this worktree's "
                  "branch). Re-run --commit from the main tree, or drop --commit.")
            return 2
        # ALL preconditions BEFORE the destructive rewrite. Deciding afterwards left
        # a detached HEAD / mid-rebase / staged-index run compacted-but-uncommitted:
        # exactly the divergence --commit exists to prevent (code review).
        blocked = commit_preflight(args.project_root)
        if blocked:
            print(f"triage_gc: --commit refused, nothing was rewritten — {_safe(blocked)}.")
            print("  Re-run without --commit to compact anyway (you must then commit it "
                  "yourself), or clear the condition above first.")
            return 2

    try:
        applied = apply_gc_reporting(args.project_root, plan["drop_ids"],
                                     backup=not args.no_backup)
    except RuntimeError as exc:
        # apply_gc refuses on malformed JSON or a log that moved under the lock. It is
        # a refusal, not a crash — print it rather than dumping a traceback out of the
        # one tool this change rewrote for legibility (code review).
        print(f"triage_gc: {_safe(exc)}")
        return 1
    _print_report(plan, applied=True)
    if not args.no_backup:
        print(f"  backup:        {applied.backup_path}")

    committed = True
    if args.commit:
        committed, note = commit_compaction(args.project_root, applied.written_text,
                                            applied.dropped)
        print(f"  {_safe(note)}")

    # Probed on the tree whose file we rewrote — not a resolved main root, which
    # would report on a file this run never touched.
    warning = describe_post_gc_divergence(args.project_root)
    if warning:
        print()
        print(_safe(warning))
    # A refused/failed/timed-out --commit is NOT success: the log is compacted and the
    # delivery channel is off, and automation reading only the exit code would take
    # that for a clean run (external code review).
    return 0 if committed else 3


if __name__ == "__main__":
    raise SystemExit(main())

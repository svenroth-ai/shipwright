#!/usr/bin/env python3
"""ensure_current — the F11 / campaign "refresh-if-behind" guard
(iterate-2026-06-12-automerge-serial-integrate — Auto-merge churn fix, Option A).

Bring an iterate branch current with ``origin/<default>`` THROUGH ``integrate_main``
(regenerating the derived snapshots) before its PR merges. GitHub's server-side
3-way auto-merge CANNOT run the regenerate-at-merge resolver, so a branch that
fell behind would merge stale (Group-E staleness) or stall DIRTY on the
regenerated-snapshot conflict. Caller:

  - F11 (every iterate, incl. campaign sub-iterates): refresh before arming
    ``gh pr merge --auto`` or handing the PR to the campaign orchestrator. The
    interleaved-serial campaign loop keeps ONE PR open at a time, so this is a
    clean no-op there — there is no separate end-stage drain.

A branch already current is a CLEAN no-op — ``integrate`` is never invoked
(nothing fetched-merged-committed) — so the common single-iterate auto-merge path
is unchanged. Thin wrapper over ``integrate_main.integrate`` (kept here, not in
integrate_main.py, so neither file crosses the 300-LOC bloat guideline).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.churn_merge import TRIAGE_LOG  # noqa: E402
from lib.main_tree_guards import op_in_progress  # noqa: E402
from lib.triage_validate import validate_triage_text  # noqa: E402
from tools import integrate_main  # noqa: E402


def _diag(message: str) -> None:
    try:
        sys.stderr.write(f"{message}\n")
    except Exception:  # noqa: BLE001 — a failed diagnostic must not crash the guard
        pass


def _behind_count(project_root: Path, ref: str) -> int | None:
    """Commits on ``ref`` not reachable from HEAD (``git rev-list --count HEAD..ref``).
    0 ⇒ HEAD is current/ahead; >0 ⇒ behind. None when the count can't be read."""
    proc = integrate_main._git(project_root, "rev-list", "--count", f"HEAD..{ref}", check=False)
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


def _absorb_dirty_triage_log(project_root: Path) -> str | None:
    """Commit an uncommitted ``triage.jsonl`` before a merge could refuse to
    start over it ("Your local changes ... would be overwritten by merge").

    A background producer (the compliance backlog, P2.43) refreshes this
    append-only log on every Stop hook for an iterate run's whole duration —
    not just once — so a finalization spanning more than one Stop can dirty it
    again after F6's own commit, in the window this guard runs in. The manual
    workaround (PR #582, two consecutive integration attempts) was to carry
    the appends onto the branch as chore commits by hand; this automates that,
    scoped to the one path, so nothing else staged or dirty rides along.

    Skipped outright, no index touched, in three cases:
    - a merge/rebase/cherry-pick/revert/bisect is already underway
      (:func:`lib.main_tree_guards.op_in_progress`, fail-closed on an
      unanswerable probe) — staging an unmerged ``UU`` path there would mark a
      real conflict resolved with its conflict markers still in the content
      (Stage-3 doubt review, medium: the narrower bare-``MERGE_HEAD`` check
      this replaced missed rebase/cherry-pick/revert/bisect and read any
      probe failure as "no operation", the wrong direction to fail);
    - the change is an untracked file (``??``) rather than a modification —
      this guard's job is absorbing a dirty TRACKED log, not deciding a fresh
      one should start being tracked (Stage-3 doubt review, low);
    - a deletion (worktree ``D``/staged ``D ``, or the path is simply gone) —
      this append-only log is never legitimately deleted by anything in the
      pipeline (external review, openai low).

    The on-disk content is also validated (:func:`lib.triage_validate.validate_triage_text`)
    before anything is staged: a torn write racing this call must not be
    committed as the log's next permanent line (Stage-3 doubt review, low —
    the sibling primitive `resolve_churn_conflicts` validates for the same
    reason before it commits).

    Best-effort and never raises. On a failed ``add``/``commit`` the index is
    left exactly as before the call (a failed ``add`` never ran; a failed
    ``commit`` is reset with ``git reset -q``), because a STAGED-but-uncommitted
    log is a strictly worse state than the dirty one this guard started from —
    a later ``git merge --abort`` can refuse on a staged, not-up-to-date path
    the same way the original merge did (Stage-3 doubt review, medium). The
    git stderr for either failure is written to stderr (never into the
    returned step token, which the caller's `steps` list treats as a fixed
    vocabulary) so a failure is diagnosable rather than indistinguishable from
    the pre-fix symptom.
    """
    if op_in_progress(project_root):
        return "triage-absorb-skipped-op-in-progress"
    status = integrate_main._git(project_root, "status", "--porcelain", "--", TRIAGE_LOG, check=False)
    lines = (status.stdout or "").splitlines()
    if status.returncode != 0 or not lines:
        return None
    if lines[0][:2] == "??":
        return None
    if not (project_root / TRIAGE_LOG).exists():
        return None
    try:
        text = (project_root / TRIAGE_LOG).read_text(encoding="utf-8")
    except OSError:
        return None
    if validate_triage_text(text):
        return "triage-absorb-skipped-invalid"
    add = integrate_main._git(project_root, "add", "--", TRIAGE_LOG, check=False)
    if add.returncode != 0:
        _diag(f"[ensure_current] triage absorb: git add failed: {add.stderr.strip()[:300]}")
        return "triage-absorb-add-failed"
    commit = integrate_main._git(
        project_root, "commit", "-m", "chore(triage): absorb background triage writes",
        "--", TRIAGE_LOG, check=False,
    )
    if commit.returncode == 0:
        return "triage-absorbed"
    integrate_main._git(project_root, "reset", "-q", "--", TRIAGE_LOG, check=False)
    _diag(f"[ensure_current] triage absorb: commit failed: {commit.stderr.strip()[:300]}")
    return "triage-absorb-commit-failed"


def ensure_current(
    project_root: Path,
    run_id: str,
    *,
    merge_ref: str | None = None,
    default_branch: str | None = None,
    session_id: str | None = None,
    reason: str = "ensure-current pre-merge refresh",
    do_fetch: bool = True,
    regenerate: bool = True,
) -> dict:
    """Refresh-if-behind. Returns the JSON contract the F11 + campaign prose parse::

        {"status", "action": "already-current"|"integrated"|<failure-status>,
         "behind": int|None, "integrated": bool, "steps": [...]}

    ``integrated`` is True only when a commit was actually made, so the caller
    knows to re-push. ``action == already-current`` ⇒ the guard added nothing.
    """
    project_root = Path(project_root).resolve()
    steps: list[str] = []

    if do_fetch and os.environ.get("SHIPWRIGHT_ITERATE_NO_FETCH") != "1":
        fetched = integrate_main._git(project_root, "fetch", "origin", check=False)
        steps.append("fetched" if fetched.returncode == 0 else "fetch-failed")

    # Absorb FIRST — before the ref/behind checks below, not just before the
    # merge. `ensure_current` is also invoked when the branch is ALREADY
    # current (the delivery-ladder's repeat refresh calls), which is exactly
    # the state a long finalization's background writes accumulate in
    # BETWEEN calls; skipping the absorb there would silently lose them at
    # worktree teardown — the same failure class the rejected outbox-routing
    # alternative was rejected for (Stage-3 doubt review, high). Captured
    # BEFORE the absorb: `made_commit` below (comparing before/after) must see
    # an absorb commit too, or a race where `integrate()` then finds itself
    # already-current reports `integrated=False` while HEAD genuinely
    # advanced (Stage-2 code review, medium).
    head_before = integrate_main._git(project_root, "rev-parse", "HEAD", check=False).stdout.strip()
    absorbed = _absorb_dirty_triage_log(project_root)
    if absorbed:
        steps.append(absorbed)
    # An absorb-only advance (no merge needed/attempted below) still counts:
    # the caller gates re-push on `integrated`, and a commit sitting unpushed
    # is exactly what this whole guard exists to prevent.
    absorbed_only_integrated = absorbed == "triage-absorbed"

    branch = default_branch or integrate_main._default_branch(project_root)
    ref = merge_ref or f"origin/{branch}"
    if integrate_main._git(
        project_root, "rev-parse", "--verify", "--quiet", ref, check=False
    ).returncode != 0:
        return {"status": "bad_ref", "ref": ref, "action": "bad_ref",
                "behind": None, "integrated": absorbed_only_integrated, "steps": steps}

    behind = _behind_count(project_root, ref)
    if behind == 0:
        steps.append("already-current")
        return {"status": "ok", "action": "already-current", "behind": 0,
                "integrated": absorbed_only_integrated, "steps": steps}

    # Behind (or count unreadable → integrate defensively; integrate() no-ops if it
    # turns out to be an ancestor). do_fetch=False: we already fetched above.
    result = integrate_main.integrate(
        project_root, run_id,
        merge_ref=ref, default_branch=branch, session_id=session_id,
        reason=reason, do_fetch=False, regenerate=regenerate,
    )
    head_after = integrate_main._git(project_root, "rev-parse", "HEAD", check=False).stdout.strip()
    # Did the branch actually move? Compare HEAD before/after rather than inferring
    # from integrate()'s internal step names — `integrated` is load-bearing (a
    # missed re-push would let auto-merge merge a STALE branch), so decouple it
    # from that step vocabulary so a future integrate() success path can't silently
    # flip it false while HEAD really advanced.
    made_commit = bool(head_before) and head_before != head_after
    if result.get("status") != "ok":
        action = result.get("status", "error")
    elif made_commit:
        action = "integrated"
    else:
        action = "already-current"  # race: count read >0 but ref was an ancestor by merge time

    merged = dict(result)
    merged["action"] = action
    merged["behind"] = behind
    merged["integrated"] = result.get("status") == "ok" and made_commit
    merged["steps"] = steps + result.get("steps", [])
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh an iterate branch with origin/<default> if behind, before it merges"
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--merge-ref", default=None, help="override merge source (default origin/<default>)")
    parser.add_argument("--default-branch", default=None)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--reason", default="ensure-current pre-merge refresh")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--no-regenerate", action="store_true")
    args = parser.parse_args(argv)

    result = ensure_current(
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
    # Reuse integrate_main's status→exit mapping so the two CLIs agree on codes
    # (ok→0, blocked→2, events/triage_invalid→4, bad_ref→5, merge_failed→6,
    # merge_commit_failed*→7, followup_commit_failed→8, ledger_writeback_failed→9,
    # else→3). already-current carries status "ok" → 0, the guard's happy path.
    #
    # The 9 was MISSING here while the comment already claimed the two agreed, so a lost
    # run ledger exited 3 from this CLI and 9 from the other — and F11 prints "non-churn
    # source conflict?" for anything non-zero, which is the wrong diagnosis for a merge
    # that already landed. Found by the Stage-3 doubt review of P2.15, which made the
    # status reachable for a second path; the drift itself predates that change.
    status = result.get("status")
    if status == "ok":
        return 0
    if status == "blocked":
        print(f"ABORT: non-churn conflicts — resolve by hand: {result.get('blocking')}", file=sys.stderr)
        return 2
    if status in ("events_invalid", "triage_invalid"):
        return 4
    if status == "bad_ref":
        print(f"ABORT: merge ref does not resolve: {result.get('ref')}", file=sys.stderr)
        return 5
    if status == "merge_failed":
        return 6
    if status in ("merge_commit_failed", "merge_commit_failed_abort_incomplete"):
        return 7
    if status == "followup_commit_failed":
        return 8
    if status == "ledger_writeback_failed":
        print(f"ABORT: {result.get('message')}: {result.get('failed')}", file=sys.stderr)
        return 9
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

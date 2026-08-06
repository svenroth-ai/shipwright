"""Git-state preconditions for a tool that is about to COMMIT in the operator's
main tree.

Extracted from :mod:`lib.reconcile_triage` (which sits exactly at the 300-LOC
guideline) so a second caller — ``tools/triage_gc.py --commit`` — can share one
copy rather than grow a third. ``reconcile_triage`` re-exports all three under
their historical private names, so its import path and call sites are unchanged.

Every predicate answers in the **fail-closed** direction: a probe git could not
answer reads as "yes, the hazard is present", so the caller skips. An unanswered
question must never license a commit into a half-finished operation.

**Not** covered here, so a caller cannot assume it is: nothing probes
``.git/index.lock``. No guard did before the extraction either — an external
review round suspected one had been dropped, and the answer is that there never
was one. A stranded lock surfaces as a non-zero return from the commit itself.
``lib.sweep_outbox`` still carries its own byte-identical ``_op_in_progress``
copy (audit 2026-07-28 finding 29, out of this change's scope).
"""

from __future__ import annotations

from pathlib import Path

import subprocess

from lib.git_base import TIMEOUT_RETURNCODE, run_git_soft

#: Returned by :func:`_probe` when git could not be RUN at all. Distinct from any real
#: git exit code so a caller cannot confuse "git said no" with "there was no git".
_UNRUNNABLE = -9001


def _probe(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """``run_git_soft`` that also survives git being absent.

    ``run_git_soft`` maps a TIMEOUT but lets ``FileNotFoundError`` out, and these
    predicates run in a tool that has already rewritten a tracked file by the time some
    of them are called — a traceback there leaves the operator with a compacted log and
    a stack trace instead of a remedy (doubt review).
    """
    try:
        return run_git_soft(args, cwd=cwd)
    except OSError as exc:
        return subprocess.CompletedProcess(["git", *args], _UNRUNNABLE, "", str(exc))


def op_in_progress(main_root: Path) -> bool:
    """True when a merge / rebase / cherry-pick / revert / bisect is underway —
    committing into a half-finished operation would corrupt it."""
    # MERGE_HEAD / CHERRY_PICK_HEAD / REVERT_HEAD are pseudo-refs rev-parse can
    # resolve; rebase-merge/rebase-apply and BISECT_LOG are git-dir FILES, so
    # they must be probed by path (rev-parse --verify can't resolve a file).
    for ref in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        probe = _probe(["rev-parse", "--verify", "--quiet", ref], main_root)
        if probe.returncode == 0:
            return True
        # Unknown state must not read as "no operation in progress" — that would
        # commit into a half-finished merge on an unanswered question.
        if probe.returncode in (TIMEOUT_RETURNCODE, _UNRUNNABLE):
            return True
    for rel in ("rebase-merge", "rebase-apply", "BISECT_LOG"):
        probe = _probe(["rev-parse", "--git-path", rel], main_root)
        # A timeout must NOT fall into the `continue` below: `continue` means "this
        # marker is absent", which is a definite answer to a question git never
        # answered. A rebase sets none of the pseudo-refs above, so this loop is the
        # ONLY thing that detects one — reading a timeout as absence here is what
        # would let the commit land inside a half-finished rebase.
        if probe.returncode in (TIMEOUT_RETURNCODE, _UNRUNNABLE):
            return True
        if probe.returncode != 0:
            continue
        # --git-path may return a relative (``.git/...``) OR absolute path
        # (linked worktree / non-standard git-dir). Resolve each correctly.
        p = Path(probe.stdout.strip())
        full = p if p.is_absolute() else main_root / p
        if full.exists():
            return True
    return False


def is_detached(main_root: Path) -> bool:
    """True when HEAD is detached — a commit there is unreferenced and would be
    lost, so the caller must skip rather than create one."""
    # Any non-zero, timeout included, reads as detached → the caller skips.
    return _probe(["symbolic-ref", "--quiet", "HEAD"], main_root).returncode != 0


def has_staged_changes(main_root: Path) -> bool:
    """True when ANYTHING is staged in the index. We skip rather than risk a
    partial ``git commit -- <path>`` interacting with a user's staged WIP — or,
    if ``triage.jsonl`` itself is staged, committing a hand-staged index state we
    never validated. The drift we act on is always UNSTAGED background appends,
    so a non-empty index means "not our case" → no-op (AC-3)."""
    # Any non-zero, timeout included, reads as "something is staged" → skip.
    return _probe(["diff", "--cached", "--quiet"], main_root).returncode != 0


def path_state_vs_head(main_root: Path, rel_path: str) -> str:
    """``"clean"`` | ``"dirty"`` | ``"unknown"`` | ``"not_a_repo"`` for ``rel_path``.

    ``triage_gc --commit`` needs this and the three predicates above do not give
    it: they answer about the index and the repo's operation state, not about
    whether THIS file already carried uncommitted drift before we touched it. A
    compaction committed over pre-existing background appends would fold
    undelivered operator data into a commit whose subject says "compact"
    (external plan review, round 2).

    Three states, not a ``bool | None``: the two consumers need OPPOSITE fail
    directions from the same probe, so collapsing "could not ask" into either
    answer is wrong for one of them. ``--commit`` must refuse on ``unknown``
    (fail-closed), while the post-apply warning must SPEAK on ``unknown`` — a
    non-empty drop set means lines were removed, so silence there would hide the
    very divergence AC-1 exists to announce. An earlier cut returned ``False`` for
    any non-zero, which made a non-git directory print the full "the sweep will
    deliver NOTHING" text; that is the conflation ``reconcile_triage._has_drift``
    was hardened against (code review).
    """
    # "not a git repository" is its OWN answer, not "unknown": the GC engine works on
    # any directory holding a triage store, and before this change `--apply` there made
    # no git call at all. Reporting `unknown` made a plain directory print the full "the
    # sweep will deliver NOTHING on every iterate" text, which is not true of it
    # (doubt review).
    inside = _probe(["rev-parse", "--git-dir"], main_root)
    if inside.returncode == _UNRUNNABLE:
        return "unknown"
    if inside.returncode != 0:
        return "not_a_repo"
    for args in (["diff", "--quiet", "--", rel_path],
                 ["diff", "--cached", "--quiet", "--", rel_path]):
        probe = _probe(args, main_root)
        if probe.returncode not in (0, 1):
            # git reserves 0/1 for "no differences"/"differences found"; ANYTHING else
            # is a question we did not get answered — 128 (not a repo, bad pathspec),
            # the timeout sentinel, and a NEGATIVE code from a signalled git, which a
            # `> 1` test silently classified as "dirty" and then advised running
            # reconcile_main_triage.py, which would not have helped (doubt review).
            return "unknown"
        if probe.returncode != 0:
            return "dirty"
    return "clean"

"""Guarded commit-path for uncommitted main-tree ``.shipwright/triage.jsonl``
background drift.

``.shipwright/triage.jsonl`` is tracked (campaign 2026-06-05-track-triage-jsonl
C1), main-repo-root durable, and written by per-session BACKGROUND producers
(plugin-sync Stop-hook, compliance audit, ``triage_add``). C2's leak-guard
*exemption* stops those main-tree writes from tripping the F0/F11 isolation
guard but is **not a commit path** — the appends accumulate uncommitted, orphan
(new worktrees branch off ``origin/<default>``), and eventually block
``git merge --ff-only origin/main`` / ``git pull`` in the main tree (hit
2026-06-07). See ``.shipwright/planning/iterate/2026-06-07-triage-main-tree-reconcile.md``.

:func:`reconcile_main_triage` folds that drift into ONE ``chore(triage)`` commit
(B7-exempt — Rule E non-functional type) BEFORE a caller's FF/pull, reusing C2's
``validate_triage_text`` + ``dedup_triage_lines``. It is **safe-by-default**: a
batch of guards make it a structured no-op rather than ever corrupting git state,
and it serializes against background producers via the canonical triage lock.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Wire up shared/scripts so sibling lib/ + triage import regardless of caller.
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

import triage  # noqa: E402  — reuse the canonical producer lock (see _triage_lock)
from lib.churn_merge import TRIAGE_LOG, dedup_triage_lines, validate_triage_text  # noqa: E402
from lib.worktree_isolation import GitError, main_repo_root, run_git  # noqa: E402

#: Truthy spellings of ``$CI`` that disable the auto-commit unless ``allow_ci``.
_CI_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass
class ReconcileResult:
    """Outcome of :func:`reconcile_main_triage`.

    ``status`` ∈ {``committed``, ``no_drift``, ``skipped``, ``invalid``,
    ``error``}. ``reason`` carries the guard name for ``skipped`` /
    ``error``; ``folded`` is the count of genuinely-new (deduped) lines in a
    ``committed`` run; ``errors`` holds validator messages for ``invalid``.
    """

    status: str
    reason: str = ""
    folded: int = 0
    commit_subject: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "folded": self.folded,
            "commit_subject": self.commit_subject,
            "errors": self.errors,
        }


def _ci_active() -> bool:
    return os.environ.get("CI", "").strip().lower() in _CI_TRUTHY


def _op_in_progress(main_root: Path) -> bool:
    """True when a merge / rebase / cherry-pick / revert / bisect is underway —
    committing into a half-finished operation would corrupt it."""
    # MERGE_HEAD / CHERRY_PICK_HEAD / REVERT_HEAD are pseudo-refs rev-parse can
    # resolve; rebase-merge/rebase-apply and BISECT_LOG are git-dir FILES, so
    # they must be probed by path (rev-parse --verify can't resolve a file).
    for ref in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        if run_git(["rev-parse", "--verify", "--quiet", ref], cwd=main_root, check=False).returncode == 0:
            return True
    for rel in ("rebase-merge", "rebase-apply", "BISECT_LOG"):
        probe = run_git(["rev-parse", "--git-path", rel], cwd=main_root, check=False)
        if probe.returncode != 0:
            continue
        # --git-path may return a relative (``.git/...``) OR absolute path
        # (linked worktree / non-standard git-dir). Resolve each correctly.
        p = Path(probe.stdout.strip())
        full = p if p.is_absolute() else main_root / p
        if full.exists():
            return True
    return False


def _is_detached(main_root: Path) -> bool:
    return run_git(["symbolic-ref", "--quiet", "HEAD"], cwd=main_root, check=False).returncode != 0


def _has_staged_changes(main_root: Path) -> bool:
    """True when ANYTHING is staged in the index. We skip rather than risk a
    partial ``git commit -- <path>`` interacting with a user's staged WIP — or,
    if ``triage.jsonl`` itself is staged, committing a hand-staged index state we
    never validated. The drift we act on is always UNSTAGED background appends,
    so a non-empty index means "not our case" → no-op (AC-3)."""
    return run_git(["diff", "--cached", "--quiet"], cwd=main_root, check=False).returncode != 0


def _has_drift(main_root: Path) -> bool:
    out = run_git(["status", "--porcelain", "--", TRIAGE_LOG], cwd=main_root, check=False).stdout
    return bool(out.strip())


def _head_line_set(main_root: Path) -> set[str]:
    """Stripped non-blank lines of ``HEAD:<triage>`` (empty if absent). Used to
    count genuinely-new lines; comparison is whitespace-normalised so a CRLF vs
    LF difference doesn't inflate the count."""
    proc = run_git(["show", f"HEAD:{TRIAGE_LOG}"], cwd=main_root, check=False)
    if proc.returncode != 0:
        return set()
    return {ln.strip() for ln in proc.stdout.split("\n") if ln.strip()}


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` verbatim (UTF-8, no newline translation) via tempfile +
    os.replace so a concurrent reader never sees a torn file."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def reconcile_main_triage(
    project_root: Path | str,
    *,
    allow_ci: bool = False,
) -> ReconcileResult:
    """Fold uncommitted main-tree ``triage.jsonl`` drift into one ``chore(triage)``
    commit, then return. Resolves the MAIN repo root from ``project_root`` (so it
    is correct when called from inside a worktree). Never raises for an expected
    condition — returns a structured :class:`ReconcileResult` instead.

    **Manual fallback only (campaign 2026-06-08-triage-outbox-delivery / D2).**
    The per-iterate default is now the branch SWEEP (:mod:`lib.sweep_outbox`,
    wired into ``setup_iterate_worktree``); idle-main background producers route
    to the gitignored outbox, never the tracked log, so neither ``setup`` nor
    ``integrate_main`` calls this anymore. It survives ONLY as the operator
    ``reconcile_main_triage.py`` CLI — "unblock a hand pull, no imminent iterate".
    """
    root = Path(project_root)

    # --- resolve main root (also our not-a-git-repo probe) ------------------
    # main_repo_root is the one helper that runs git with check=True; a GitError
    # means "not a git repo", while a hung git (TimeoutExpired) / filesystem
    # error must still honour the "never raises for an expected condition"
    # contract → map to a structured error rather than propagating.
    try:
        main_root = main_repo_root(root)
    except GitError:
        return ReconcileResult(status="skipped", reason="not_a_git_repo")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ReconcileResult(status="error", reason=f"git_probe_failed: {exc}")

    # --- cheap guards (no lock needed) -------------------------------------
    if _ci_active() and not allow_ci:
        return ReconcileResult(status="skipped", reason="ci_without_optin")
    # op-in-progress before detached-HEAD: a rebase detaches HEAD, so checking
    # detached first would mask the more actionable "op_in_progress" reason.
    if _op_in_progress(main_root):
        return ReconcileResult(status="skipped", reason="op_in_progress")
    if _is_detached(main_root):
        return ReconcileResult(status="skipped", reason="detached_head")
    if _has_staged_changes(main_root):
        return ReconcileResult(status="skipped", reason="staged_changes")
    if not _has_drift(main_root):
        return ReconcileResult(status="no_drift")

    # --- critical section: exclude background producers via the canonical
    #     triage lock (same primitive triage_add / the Stop-hook contend on, so
    #     a dedup-rewrite can't clobber a concurrent append). Held through the
    #     commit so the committed bytes match what we validated.
    # Couple to triage.py's SSoT path helpers so we lock the BYTE-IDENTICAL path
    # the background producers contend on — mutual exclusion would silently break
    # if TRIAGE_FILE changed and we hardcoded the path here.
    triage_path = triage._triage_path(main_root)
    lock_path = triage._lock_path(main_root)
    with triage._FileLock(lock_path):
        if not _has_drift(main_root):  # re-check under lock (a producer may have just committed-clean)
            return ReconcileResult(status="no_drift")
        if not triage_path.exists():
            # Drift is a DELETION of the tracked log (or a sparse/partial
            # checkout). Don't auto-commit a deletion — leave it for the operator.
            return ReconcileResult(status="skipped", reason="triage_missing")
        try:
            with triage_path.open("r", encoding="utf-8", newline="") as fh:
                raw = fh.read()
        except OSError as exc:
            return ReconcileResult(status="error", reason=f"read_failed: {exc}")

        # Dedup FIRST (collapse byte-identical double-writes), THEN validate the
        # result — the order the churn resolver uses, so an exact-dup append
        # doesn't false-trip the validator's "duplicate append for id" check.
        #
        # Line endings: a CRLF-checked-out file (autocrlf=true on Windows) that a
        # LF-writing producer appended to has MIXED endings, so a naive exact-line
        # dedup would see ``dup\r`` ≠ ``dup`` and miss the duplicate. Normalise by
        # stripping a trailing ``\r`` before dedup, then re-emit with the file's
        # existing EOL style so we introduce no spurious whole-file diff.
        eol = "\r\n" if "\r\n" in raw else "\n"
        lines = [ln[:-1] if ln.endswith("\r") else ln for ln in raw.split("\n")]
        if lines and lines[-1] == "":
            lines = lines[:-1]  # drop the artifact of a trailing newline
        deduped, _ = dedup_triage_lines(lines)
        deduped_text = (eol.join(deduped) + eol) if deduped else ""

        errors = validate_triage_text(deduped_text)
        if errors:
            return ReconcileResult(status="invalid", errors=errors)

        if deduped_text != raw:
            _atomic_write(triage_path, deduped_text)

        # A dedup-only change may now match HEAD exactly → nothing to commit.
        if not _has_drift(main_root):
            return ReconcileResult(status="no_drift")

        head = _head_line_set(main_root)
        folded = sum(1 for ln in deduped if ln.strip() and ln.strip() not in head)
        subject = f"chore(triage): fold {folded} main-tree background append(s)"
        # ``git commit -- <path>`` commits the WORKING-TREE content of that path
        # (the append-only log's latest superset) and ignores the index for it;
        # _unrelated_staged already guaranteed no OTHER path is staged, so this
        # never sweeps up unrelated work nor drops an index-only delta of a file
        # that is, by the log's append-only nature, always a superset on disk.
        commit = run_git(
            ["commit", "-m", subject, "--", TRIAGE_LOG], cwd=main_root, check=False
        )
        if commit.returncode != 0:
            return ReconcileResult(status="error", reason=f"commit_failed: {commit.stderr.strip()[:300]}")
        return ReconcileResult(status="committed", folded=folded, commit_subject=subject)

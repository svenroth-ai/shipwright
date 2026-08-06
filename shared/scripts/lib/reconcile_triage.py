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

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Wire up shared/scripts so sibling lib/ + triage import regardless of caller.
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

import triage  # noqa: E402  — reuse the canonical producer lock (see _triage_lock)
from lib.churn_merge import TRIAGE_LOG, dedup_triage_lines, validate_triage_text  # noqa: E402
from lib.ci_env import ci_active  # noqa: E402
from lib.git_base import HOOK_GIT_TIMEOUT, TIMEOUT_RETURNCODE, run_git_soft  # noqa: E402
# The dedup rewrite's durable writer + its rollback live in lib.reconcile_rollback
# (extracted to keep this file under the 300-LOC guideline; the rollback is audit
# 2026-07-28 finding 16). ``_atomic_write`` keeps its historical private name here.
from lib.reconcile_rollback import (  # noqa: E402
    atomic_write_verbatim as _atomic_write,
    head_oid as _head_oid,
    rollback_failed_commit as _rollback_failed_commit,
)
# The three main-tree commit preconditions moved to lib.main_tree_guards so
# tools/triage_gc.py --commit shares one copy instead of adding a third (this file
# is at the 300-LOC guideline). Re-exported under their historical private names.
from lib.main_tree_guards import (  # noqa: E402,F401  (re-export: see lib/main_tree_guards.py)
    has_staged_changes as _has_staged_changes,
    is_detached as _is_detached,
    op_in_progress as _op_in_progress,
)
from lib.worktree_isolation import GitError, main_repo_root  # noqa: E402


@dataclass
class ReconcileResult:
    """Outcome of :func:`reconcile_main_triage`.

    ``status`` ∈ {``committed``, ``no_drift``, ``skipped``, ``invalid``,
    ``error``}. ``reason`` carries the guard name for ``skipped`` /
    ``error``; ``folded`` is the count of genuinely-new (deduped) lines in a
    ``committed`` run; ``errors`` holds validator messages for ``invalid``;
    ``warnings`` holds whatever :mod:`lib.triage_dedup` reported about the dedup
    (a same-id ``append`` collapse, or an id collision it refused to collapse) —
    informational, never a reason to fail. This caller used to discard them.
    """

    status: str
    reason: str = ""
    folded: int = 0
    commit_subject: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "folded": self.folded,
            "commit_subject": self.commit_subject,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _ci_active() -> bool:
    """Delegates to the shared leaf — see :mod:`lib.ci_env` for why this is not
    a local copy."""
    return ci_active()


def _has_drift(main_root: Path) -> bool | None:
    """True/False, or ``None`` when git could not be asked.

    ``None``, not ``False``, for EVERY failure: this runs inside the canonical lock in
    the MAIN tree, and ``git status --porcelain`` refreshes the index (taking
    ``.git/index.lock``). An unanswered probe reporting "no drift" would have the
    caller return ``no_drift`` over a log that has some.
    """
    proc = run_git_soft(["status", "--porcelain", "--", TRIAGE_LOG], cwd=main_root)
    if proc.returncode != 0:
        # ANY non-zero, not just a timeout: `git status` has no legitimate non-zero
        # outcome here, so a failure leaves stdout empty and `bool("")` would report a
        # confident "no drift" from an unanswered probe (external review, GPT).
        return None
    return bool(proc.stdout.strip())


def _head_line_set(main_root: Path) -> set[str] | None:
    """Stripped non-blank lines of ``HEAD:<triage>`` (empty if absent, ``None`` when
    git could not be asked). Used to
    count genuinely-new lines; comparison is whitespace-normalised so a CRLF vs
    LF difference doesn't inflate the count."""
    proc = run_git_soft(["show", f"HEAD:{TRIAGE_LOG}"], cwd=main_root)
    if proc.returncode == TIMEOUT_RETURNCODE:
        # ``None``, not an empty set: empty means "HEAD holds nothing", which would
        # count every existing line as newly folded and misreport the total.
        return None
    if proc.returncode != 0:
        return set()
    return {ln.strip() for ln in proc.stdout.split("\n") if ln.strip()}


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
    drift_probe = _has_drift(main_root)
    if drift_probe is None:
        return ReconcileResult(status="error", reason="git_timeout: status --porcelain")
    if not drift_probe:
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
        drift_probe = _has_drift(main_root)  # re-check under lock (a producer may have just committed-clean)
        if drift_probe is None:
            return ReconcileResult(status="error", reason="git_timeout: status --porcelain")
        if not drift_probe:
            return ReconcileResult(status="no_drift")
        if not triage_path.exists():
            # Drift is a DELETION of the tracked log (or a sparse/partial
            # checkout). Don't auto-commit a deletion — leave it for the operator.
            return ReconcileResult(status="skipped", reason="triage_missing")
        try:
            # ``errors="surrogateescape"`` for the same reason the sweep readers use it:
            # an interrupted append truncates the log mid multi-byte sequence, and a
            # STRICT decode raises ``UnicodeDecodeError`` — which is a ``ValueError``,
            # NOT an ``OSError``, so it escaped the handler below and crashed the caller
            # rather than producing the structured ``read_failed`` this path promises.
            # ``ValueError`` is caught too, so any residual decode/seek failure lands in
            # the structured result instead of propagating.
            with triage_path.open(
                "r", encoding="utf-8", newline="", errors="surrogateescape"
            ) as fh:
                raw = fh.read()
        except (OSError, ValueError) as exc:
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
        deduped, warnings = dedup_triage_lines(lines)
        deduped_text = (eol.join(deduped) + eol) if deduped else ""

        errors = validate_triage_text(deduped_text)
        if errors:
            return ReconcileResult(status="invalid", errors=errors, warnings=warnings)

        rewrote = deduped_text != raw
        if rewrote:
            _atomic_write(triage_path, deduped_text)

        # A dedup-only change may now match HEAD exactly → nothing to commit.
        drift_probe = _has_drift(main_root)
        if drift_probe is None:
            return ReconcileResult(status="error", reason="git_timeout: status --porcelain",
                                   warnings=warnings)
        if not drift_probe:
            return ReconcileResult(status="no_drift", warnings=warnings)

        head = _head_line_set(main_root)
        if head is None:
            return ReconcileResult(status="error", reason="git_timeout: show HEAD",
                                   warnings=warnings)
        head_before = _head_oid(main_root)   # "" when git could not answer → no rollback
        folded = sum(1 for ln in deduped if ln.strip() and ln.strip() not in head)
        subject = f"chore(triage): fold {folded} main-tree background append(s)"
        # ``git commit -- <path>`` commits the WORKING-TREE content of that path
        # (the append-only log's latest superset) and ignores the index for it;
        # _unrelated_staged already guaranteed no OTHER path is staged, so this
        # never sweeps up unrelated work nor drops an index-only delta of a file
        # that is, by the log's append-only nature, always a superset on disk.
        # 120 s + a TimeoutExpired handler, mirroring the sibling sweep commit
        # (``sweep_outbox``), which documents why: this commit fires the bloat
        # pre-commit hook, whose cold ``uv run`` routinely exceeds run_git's 15 s
        # default. Two consequences made the default actively dangerous HERE rather
        # than merely slow: run_git kills the process on timeout, which strands
        # ``.git/index.lock`` — and unlike the sweep, this commit runs in the MAIN
        # tree, so the stranded lock blocks the operator's own repo, not a scratch
        # worktree. There was also no handler at all, so it crashed the caller
        # instead of returning the structured error every other path here returns.
        commit = run_git_soft(
            ["commit", "-m", subject, "--", TRIAGE_LOG],
            cwd=main_root, timeout=HOOK_GIT_TIMEOUT,
        )
        if commit.returncode == TIMEOUT_RETURNCODE:
            # NO rollback here, deliberately. run_git KILLS on timeout, so we do not know
            # whether the commit landed, and restoring the pre-dedup bytes over a commit
            # that DID land would put the log back out of sync with HEAD — the very state
            # this rollback exists to avoid. Say what is unknown, including the lock the
            # kill may have stranded; do not touch it (it may be another process's).
            return ReconcileResult(
                status="error", warnings=warnings,
                reason="commit_timeout: the dedup rewrite is UNCOMMITTED and was not rolled back "
                       "(the commit was killed, so whether it landed is unknown). Until this is "
                       "resolved the tracked log may not be an append-only extension of HEAD, and "
                       "the outbox sweep will refuse `main_tracked_diverged` on every iterate. "
                       "Check `git status` and `git log -1`; a stranded .git/index.lock is the "
                       "other thing to look for.",
            )
        if commit.returncode != 0:
            return ReconcileResult(
                status="error", warnings=warnings,
                reason=_rollback_failed_commit(
                    triage_path, main_root, head_before,
                    rewrote=rewrote, expected=deduped_text, original=raw,
                    stderr=commit.stderr.strip()[:300],
                ),
            )
        return ReconcileResult(status="committed", folded=folded, commit_subject=subject,
                               warnings=warnings)

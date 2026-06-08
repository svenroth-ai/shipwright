"""Sweep the gitignored main-tree triage outbox into the iterate PR branch.

Campaign 2026-06-08-triage-outbox-delivery / D2. The D1 outbox
(``.shipwright/triage.outbox.jsonl``) is a per-tree, GITIGNORED buffer that
idle-main background producers append to (so the tracked log never accrues
drift). D2 DELIVERS those buffered appends: at iterate-worktree setup, the
outbox lines are folded into the *worktree's* tracked ``triage.jsonl`` and
committed on the ``iterate/<slug>`` branch — so they ride the PR to ``origin``
and ``main`` never gets a local fold commit (which previously orphaned on local
main and piled up; Codex Q1).

Two invariants make this loss-proof:

* **Whole-section lock (Codex Q4):** the canonical triage ``_FileLock`` is held
  across read-outbox -> read-worktree-tracked -> materialize -> branch-commit ->
  GC. A concurrent background producer appending to the outbox serializes
  against the ENTIRE sweep — it is never read-then-lost.
* **Origin-delivered GC (Codex unlisted failure mode):** an outbox line is
  dropped ONLY once it is present in ``origin/<default>``'s tracked log — by
  semantic ``id`` for append lines (serialization-drift-immune, FIX B) and by
  normalized text for status lines (see :mod:`lib.sweep_gc`). A just-swept line
  is on the branch but not yet in origin, so it STAYS in the outbox; an
  abandoned/deleted branch re-sweeps it next setup. Re-sweeping is harmless —
  ``merge=union`` + dedup collapses it to exactly-once. NEVER reset-after-read.

The EOL-normalize + ``dedup_triage_lines`` + ``validate_triage_text`` pipeline
is IDENTICAL to :mod:`lib.reconcile_triage` (Codex Q3) so the materialized
bytes are byte-compatible with the union merge driver.
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

import triage  # noqa: E402  — canonical lock + outbox path SSoT
from lib.churn_merge import TRIAGE_LOG, dedup_triage_lines, validate_triage_text  # noqa: E402
from lib.sweep_gc import is_delivered, parse_delivered  # noqa: E402
from lib.worktree_isolation import run_git  # noqa: E402

#: Truthy spellings of ``$CI`` that disable the auto-commit unless ``allow_ci``.
_CI_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass
class SweepResult:
    """Outcome of :func:`sweep_outbox_to_branch`.

    ``status`` ∈ {``committed``, ``no_change``, ``skipped``, ``invalid``,
    ``error``}. ``reason`` carries the guard name for ``skipped`` / ``error``;
    ``swept`` is the count of genuinely-new (deduped) lines folded into the
    branch on a ``committed`` run; ``gc_dropped`` is the count of outbox lines
    dropped because they are already origin-delivered; ``errors`` holds
    validator messages for ``invalid``.
    """

    status: str
    reason: str = ""
    swept: int = 0
    gc_dropped: int = 0
    commit_subject: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "swept": self.swept,
            "gc_dropped": self.gc_dropped,
            "commit_subject": self.commit_subject,
            "errors": self.errors,
        }


def _ci_active() -> bool:
    return os.environ.get("CI", "").strip().lower() in _CI_TRUTHY


def _op_in_progress(root: Path) -> bool:
    """True when a merge / rebase / cherry-pick / revert / bisect is underway in
    ``root`` — committing into a half-finished operation would corrupt it.
    Mirrors :func:`lib.reconcile_triage._op_in_progress`."""
    for ref in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        if run_git(["rev-parse", "--verify", "--quiet", ref], cwd=root, check=False).returncode == 0:
            return True
    for rel in ("rebase-merge", "rebase-apply", "BISECT_LOG"):
        probe = run_git(["rev-parse", "--git-path", rel], cwd=root, check=False)
        if probe.returncode != 0:
            continue
        p = Path(probe.stdout.strip())
        full = p if p.is_absolute() else root / p
        if full.exists():
            return True
    return False


def _has_staged_changes(root: Path) -> bool:
    """True when ANYTHING is staged in ``root``'s index. We skip rather than risk
    a ``git commit -- <triage>`` interacting with a user's staged WIP (AC-3 of
    reconcile)."""
    return run_git(["diff", "--cached", "--quiet"], cwd=root, check=False).returncode != 0


def _normalize_lines(raw: str) -> tuple[list[str], str]:
    """Split ``raw`` into stripped-of-CRLF lines + the file's EOL style.

    IDENTICAL idiom to :mod:`lib.reconcile_triage` (Codex Q3): strip a trailing
    ``\\r`` per line, drop the artifact empty line from a trailing newline.
    Returns ``(lines, eol)`` where ``eol`` is ``\\r\\n`` iff ``raw`` contained one.
    """
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in raw.split("\n")]
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines, eol


def _normalized_set(text: str) -> set[str]:
    """Stripped, CRLF-absorbed, non-blank line set of ``text`` (empty if falsy)."""
    if not text:
        return set()
    lines, _ = _normalize_lines(text)
    return {ln.strip() for ln in lines if ln.strip()}


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` verbatim (UTF-8, no newline translation) via tempfile +
    os.replace so a concurrent reader never sees a torn file. IDENTICAL to
    :func:`lib.reconcile_triage._atomic_write`."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _delivered_membership(main_root: Path, default_branch: str) -> tuple[set[str], set[str]]:
    """Fetch ``origin/<default>:<triage>`` and parse it into ``(append_ids, text)``
    GC anchors (see :func:`lib.sweep_gc.parse_delivered`). An outbox line is safe
    to drop only once reachable from ``origin``; membership is by semantic id for
    ``append`` lines (drift-immune, FIX B) and stripped text for status lines.
    ``check=False`` so a missing ref / file yields ``(set(), set())`` — nothing
    GC'd (fail-safe; a non-delivered id always survives)."""
    proc = run_git(
        ["show", f"origin/{default_branch}:{TRIAGE_LOG}"], cwd=main_root, check=False
    )
    if proc.returncode != 0:
        return set(), set()
    return parse_delivered(_normalized_set(proc.stdout))


def _read_text(path: Path) -> str:
    """Read ``path`` verbatim (no newline translation); empty string if absent."""
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8", newline="") as fh:
        return fh.read()


def sweep_outbox_to_branch(
    main_root: Path | str,
    worktree_path: Path | str,
    *,
    default_branch: str,
    allow_ci: bool = False,
) -> SweepResult:
    """Fold the main-tree outbox into the worktree's tracked triage log + commit
    it on the iterate branch, then GC origin-delivered outbox lines. Never raises
    for an expected condition — returns a structured :class:`SweepResult`.

    The canonical triage lock is held across the ENTIRE read->commit->GC critical
    section (Codex Q4) so a concurrent background outbox producer serializes
    against the whole sweep rather than racing a read-then-lost window.
    """
    main_root = Path(main_root)
    worktree_path = Path(worktree_path)

    # --- cheap guards (no lock needed) -------------------------------------
    if _ci_active() and not allow_ci:
        return SweepResult(status="skipped", reason="ci_without_optin")
    # The commit lands in the WORKTREE, so the op-in-progress / staged-changes
    # guards probe the worktree (not main_root): a half-finished merge or a
    # user's staged WIP THERE is what a ``git commit -- <triage>`` would corrupt.
    if _op_in_progress(worktree_path):
        return SweepResult(status="skipped", reason="op_in_progress")
    if _has_staged_changes(worktree_path):
        return SweepResult(status="skipped", reason="staged_changes")

    outbox_path = triage._outbox_path(main_root)
    worktree_triage = worktree_path / TRIAGE_LOG
    lock_path = triage._lock_path(main_root)

    # --- critical section: ONE lock across read->materialize->commit->GC ----
    with triage._FileLock(lock_path):
        outbox_raw = _read_text(outbox_path)
        outbox_lines_norm, outbox_eol = _normalize_lines(outbox_raw)
        outbox_lines = [ln for ln in outbox_lines_norm if ln.strip()]
        if not outbox_lines:
            return SweepResult(status="no_change", reason="empty_outbox")

        worktree_raw = _read_text(worktree_triage)
        worktree_lines_norm, wt_eol = _normalize_lines(worktree_raw)
        # The branch log uses the worktree file's EOL style (LF for a fresh
        # checkout); fall back to LF when the worktree log is absent/empty.
        eol = wt_eol if worktree_raw else "\n"

        # Materialize: worktree-tracked THEN outbox, deduped (first-seen order),
        # exactly the reconcile pipeline. The header (worktree line 1) is
        # preserved because it sorts first in worktree_lines.
        combined = worktree_lines_norm + outbox_lines
        deduped, _warn = dedup_triage_lines(combined)
        deduped_text = (eol.join(deduped) + eol) if deduped else ""

        errors = validate_triage_text(deduped_text)
        if errors:
            # Do NOT commit, do NOT touch the outbox — surface for the operator.
            return SweepResult(status="invalid", errors=errors)

        # Count genuinely-new lines (not already in the worktree tracked log).
        # JSONL producer lines carry NO surrounding whitespace (``json.dumps(...) +
        # "\n"``), so the stripped membership set == the exact line set here —
        # strip is a CRLF/EOL absorber, not a content mutator.
        wt_set = {ln.strip() for ln in worktree_lines_norm if ln.strip()}
        swept = sum(1 for ln in outbox_lines if ln.strip() and ln.strip() not in wt_set)

        committed_subject = ""
        if deduped_text != worktree_raw:
            worktree_triage.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(worktree_triage, deduped_text)
            add = run_git(["add", "--", TRIAGE_LOG], cwd=worktree_path, check=False)
            if add.returncode != 0:
                return SweepResult(status="error", reason=f"add_failed: {add.stderr.strip()[:300]}")
            # FIX D (D2 review cascade): gate the commit on a REAL staged delta.
            # ``deduped_text != worktree_raw`` can be EOL-only (materialized LF vs
            # a CRLF-checked-out log) that git's index — governed by autocrlf —
            # treats as NO change; committing then fails "nothing to commit" → a
            # spurious ``error``. No staged delta → git no-op → ``no_change`` (the
            # GC still runs). ``--quiet`` exits 0 when there is NO staged diff.
            staged = run_git(
                ["diff", "--cached", "--quiet", "--", TRIAGE_LOG],
                cwd=worktree_path, check=False,
            )
            if staged.returncode != 0:
                subject = f"chore(triage): sweep {swept} outbox append(s) into branch"
                # The commit fires the bloat pre-commit hook, whose cold ``uv run``
                # on a brand-new worktree routinely exceeds run_git's 15s default —
                # give it a generous timeout and map a timeout to a structured
                # error rather than letting it crash setup (never raises into setup).
                try:
                    commit = run_git(
                        ["commit", "-m", subject, "--", TRIAGE_LOG],
                        cwd=worktree_path, check=False, timeout=120.0,
                    )
                except subprocess.TimeoutExpired:
                    return SweepResult(status="error", reason="commit_timeout")
                if commit.returncode != 0:
                    return SweepResult(status="error", reason=f"commit_failed: {commit.stderr.strip()[:300]}")
                committed_subject = subject

        # --- GC (still under the lock): drop ONLY origin-delivered lines ----
        # Survivors keep the OUTBOX's OWN EOL (gitignored → no cross-platform
        # rewrite; OpenAI review). FIX B: membership is by semantic ``id`` for
        # append lines (drift-immune) + stripped text for status/unparseable lines.
        delivered_ids, delivered_text = _delivered_membership(main_root, default_branch)
        survivors = [
            ln for ln in outbox_lines
            if not is_delivered(ln.strip(), delivered_ids, delivered_text)
        ]
        gc_dropped = len(outbox_lines) - len(survivors)
        if gc_dropped:
            survivor_text = (outbox_eol.join(survivors) + outbox_eol) if survivors else ""
            _atomic_write(outbox_path, survivor_text)

        if not committed_subject:
            # Nothing folded into the branch (every outbox line already tracked);
            # report no_change unless the GC alone trimmed the outbox.
            status = "committed" if gc_dropped else "no_change"
            return SweepResult(
                status=status, reason="" if gc_dropped else "no_branch_change",
                swept=0, gc_dropped=gc_dropped,
            )

        return SweepResult(
            status="committed", swept=swept, gc_dropped=gc_dropped,
            commit_subject=committed_subject,
        )

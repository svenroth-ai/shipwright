"""Undo an uncommitted triage dedup rewrite when the commit that was meant to
publish it failed.

Extracted from :mod:`lib.reconcile_triage` (at the 300-LOC guideline); that module
re-exports :func:`atomic_write_verbatim` under its historical private name
``_atomic_write`` and calls :func:`rollback_failed_commit` from its one failure
branch.

**Why this exists — audit 2026-07-28, finding 16.** ``reconcile_main_triage``
rewrites the tracked log (dedup: it can REMOVE lines) and then commits it. There
was no rollback on any failure branch, so a failed commit left the working log a
NON-append-only extension of HEAD. ``sweep_drift.plan_main_tracked_drift`` then
refuses ``main_tracked_diverged``, and the outbox sweep — the actual delivery
channel — returns ``skipped`` on **every subsequent iterate** until someone
commits or reverts by hand. Nothing warned. The same terminal state is reachable
from ``triage_gc --apply``, which is why that tool grew its own warning in the
same change.
"""

from __future__ import annotations

from pathlib import Path

from lib.atomic_write import durable_atomic_write
from lib.git_base import run_git_soft


def head_oid(main_root: Path) -> str:
    """HEAD's oid, or ``""`` when git could not tell us — including when git is not
    installed at all. ``run_git_soft`` maps a TIMEOUT but lets ``OSError`` out, and this
    module runs on a failure path that promises a reason STRING, never a traceback
    (external code review). Callers must read ``""`` as "cannot prove HEAD is
    unchanged", which is the fail-closed direction: no rollback."""
    try:
        return run_git_soft(["rev-parse", "HEAD"], cwd=main_root).stdout.strip()
    except OSError:
        return ""


def atomic_write_verbatim(path: Path, text: str) -> None:
    """Write ``text`` verbatim (UTF-8, no newline translation) durably — tmp +
    fsync + os.replace — so a reader never sees a torn file and a crash never
    drops the content (shared :func:`durable_atomic_write`)."""
    # surrogateescape: `text` came through reconcile_triage's own surrogateescape read.
    durable_atomic_write(path, text.encode('utf-8', errors='surrogateescape'))


def rollback_failed_commit(
    triage_path: Path, main_root: Path, head_before: str, *,
    rewrote: bool, expected: str, original: str, stderr: str,
) -> str:
    """Put the dedup rewrite back, and return the ``reason`` string describing what
    actually happened.

    Restoring is only safe when we can prove we are undoing our OWN write and
    nothing else, so two conditions must both hold:

    * **HEAD has not moved.** A non-zero ``git commit`` is strong evidence that no
      commit was created, but it is not proof (external plan review), and restoring
      over a commit that DID land would re-introduce the divergence we are removing.
    * **The file on disk is still byte-for-byte what we wrote.** The WebUI writer
      uses ``proper-lockfile``, which does not compose with this store's Python byte
      lock (``triage_repair.py:30-36``), so an append can land between our write and
      here. Restoring then would DELETE it — trading a delivery outage for data loss,
      the wrong trade in a module whose whole subject is not losing records.

    When either fails, nothing is restored and the reason says so **and names the
    consequence**: a bare ``commit_failed`` is exactly what let this sit undiagnosed.

    Residual, stated rather than hidden: a writer that appends between the
    equality check and the ``os.replace`` inside :func:`atomic_write_verbatim` is
    still lost. That window is orders of magnitude smaller than the one being
    closed (no subprocess in it), but it is the same shape as the one
    ``sweep_drift_restore`` had to solve with a rename, and it is not zero.
    """
    base = f"commit_failed: {stderr}"
    if not rewrote:
        return base  # nothing was rewritten, so there is nothing to undo
    head_now = head_oid(main_root)
    if not head_before or not head_now or head_before != head_now:
        return (f"{base} — the dedup rewrite was NOT rolled back: HEAD moved (or could not be "
                "read), so the commit may have landed. The tracked log may no longer be an "
                "append-only extension of HEAD; until that is resolved the outbox sweep will "
                "refuse `main_tracked_diverged` and deliver nothing.")
    try:
        with triage_path.open("r", encoding="utf-8", newline="", errors="surrogateescape") as fh:
            on_disk = fh.read()
    except (OSError, ValueError) as exc:
        return f"{base} — rollback skipped, the tracked log could not be re-read ({exc})."
    if on_disk != expected:
        return (f"{base} — the dedup rewrite was NOT rolled back: another writer changed the "
                "tracked log after we wrote it, and restoring would destroy that append. The "
                "log is left as found; the outbox sweep will refuse `main_tracked_diverged` "
                "until someone commits or reverts it.")
    try:
        atomic_write_verbatim(triage_path, original)
    except OSError as exc:
        return (f"{base} — ROLLBACK FAILED ({exc}); the tracked log still holds the uncommitted "
                "dedup rewrite and the outbox sweep will refuse `main_tracked_diverged`.")
    return f"{base} — the dedup rewrite was rolled back; the tracked log is as it was found."

"""Report validation and rollback helpers for ``lib.layer_promotion_sweep`` —
split out purely to keep that module under the file-size guideline. These
exist to hold ``run_layer_promotion_sweep``'s "never raises, never leaves
residue" contract: every failure mode of the ``promote_required_layers.py``
subprocess call must degrade to a reported result with the worktree back at
its pre-sweep state, never propagate an exception or leave partial writes
behind for a later, unrelated commit to sweep up."""

from __future__ import annotations

from pathlib import Path

from lib.git_base import HOOK_GIT_TIMEOUT, run_git_soft
from lib.layer_promotion_sweep_result import LayerPromotionSweepResult


def extract_report_fields(report: object) -> tuple[list[str], int, list[str]]:
    """Validate the ``promote_required_layers.py`` report shape and pull out
    the three fields this module reads. ``json.loads`` only rejects a
    syntactically invalid document — a syntactically valid but wrong-shaped
    one (a JSON list, ``null``, or a ``promoted`` entry that isn't an object)
    would otherwise reach an unguarded ``.get()`` and raise past this
    module's own never-raises boundary (external review, PR #725). Raises
    :class:`ValueError` with a short reason for any invalid shape; never
    raises anything else."""
    if not isinstance(report, dict):
        raise ValueError(f"report is not a JSON object (got {type(report).__name__})")
    raw_promoted = report.get("promoted") or []
    if not isinstance(raw_promoted, list) or not all(
        isinstance(d, dict) and isinstance(d.get("fr", ""), str) for d in raw_promoted
    ):
        raise ValueError("'promoted' is not a list of objects with a string 'fr'")
    raw_escalated = report.get("escalated") or []
    if not isinstance(raw_escalated, list):
        raise ValueError("'escalated' is not a list")
    written_paths = report.get("written_spec_paths") or []
    if not isinstance(written_paths, list) or not all(isinstance(p, str) for p in written_paths):
        raise ValueError("'written_spec_paths' is not a list of strings")
    return [d.get("fr", "") for d in raw_promoted], len(raw_escalated), written_paths


def untracked_paths(worktree_path: Path) -> set[str] | None:
    """Every untracked path in the worktree, expanded to individual files
    rather than collapsed to a parent directory (``--untracked-files=all``),
    so a later snapshot can be diffed against this one to name exactly which
    files are new. Returns ``None`` if the status call itself fails — a
    caller must then treat cleanup as unsafe rather than assume the
    worktree was empty."""
    result = run_git_soft(["status", "--porcelain", "--untracked-files=all"], cwd=worktree_path)
    if result.returncode != 0:
        return None
    return {line[3:] for line in result.stdout.splitlines() if line.startswith("?? ")}


def rollback_staged(worktree_path: Path, pre_sha: str, pre_untracked: set[str] | None) -> bool:
    """Undo any write the promotion subprocess left behind — staged or not,
    tracked or a brand-new untracked file — so a failed ``add``/``commit``,
    or a subprocess that partially wrote the ledger/spec before timing out
    or reporting something unusable, never leaves residue for a later,
    unrelated commit to sweep up. ``reset --hard`` alone only reverts
    already-tracked content; a new untracked file the tool created (never
    staged) needs ``git clean`` too — but scoped to exactly the paths that
    are untracked NOW and were not already untracked in ``pre_untracked``,
    never a blanket ``clean -fd``, since that would delete unrelated
    untracked content that predates this sweep entirely (external review,
    PR #725 round 7; round 6 introduced the untracked-file cleanup this
    scopes). When the untracked baseline is unavailable (``None``, before or
    after), skip the destructive clean step rather than guess — a stray new
    file left behind is a lesser risk than deleting real user data. Returns
    whether the cleanup succeeded — a caller must escalate to
    ``rollback_failed`` when it did not, since an ordinary terminal status
    implies a clean rollback that never actually happened (external review,
    PR #725)."""
    if not pre_sha:
        return False
    reset = run_git_soft(["reset", "--hard", pre_sha], cwd=worktree_path, timeout=HOOK_GIT_TIMEOUT)
    if reset.returncode != 0:
        return False
    if pre_untracked is None:
        return True
    post_untracked = untracked_paths(worktree_path)
    if post_untracked is None:
        return True
    new_paths = sorted(post_untracked - pre_untracked)
    if not new_paths:
        return True
    clean = run_git_soft(["clean", "-fd", "--", *new_paths], cwd=worktree_path, timeout=HOOK_GIT_TIMEOUT)
    return clean.returncode == 0


def bail(
    worktree_path: Path, pre_sha: str, pre_untracked: set[str] | None,
    status: str, reason: str, promoted: list[str], escalated: int,
) -> LayerPromotionSweepResult:
    """Every non-decisive return path funnels through here once ``pre_sha``
    is known: unconditionally roll the worktree back to it — cheap and safe
    even when nothing was actually written, since ``reset --hard`` onto the
    current HEAD is a no-op and the scoped ``clean`` finds nothing new to
    remove — before reporting the given ``status``. Escalates to the loud
    ``rollback_failed`` when the rollback itself does not succeed, the one
    outcome where residue might still be sitting on this branch."""
    ok = rollback_staged(worktree_path, pre_sha, pre_untracked)
    if not ok:
        return LayerPromotionSweepResult(status="rollback_failed", reason=reason, promoted=promoted, escalated=escalated)
    return LayerPromotionSweepResult(status=status, reason=reason, promoted=promoted, escalated=escalated)


__all__ = ["extract_report_fields", "untracked_paths", "rollback_staged", "bail"]

"""Wave-scoped identity checks for run-id/worktree-root pointer resolution.

Split out of ``_run_id.py`` (300-LOC ceiling) — both functions answer "is
the shared session-keyed pointer safe to trust from THIS caller during a
live campaign wave", a distinct concern from the pointer-reading logic the
host module keeps.
"""

from __future__ import annotations

import os
from pathlib import Path

from lib.campaign_wave import is_wave_sentinel, per_unit_worktree_identity


def _pointer_targets_a_different_wave_unit(pointer_worktree: str, caller_root: Path) -> bool:
    """``True`` iff `caller_root` is itself a per-unit wave worktree and
    `pointer_worktree` names a DIFFERENT directory — i.e. the shared,
    session-keyed pointer was last written by a sibling unit.

    Code review (round 3, R5a): every unit in a wave shares one
    ``session_id``, so ``write_run_pointer`` (called once per unit by
    ``setup_unit_worktree.py``) overwrites the SAME file — last writer wins.
    Neither :func:`pointer_run_id` nor :func:`pointer_worktree_root`
    compared the pointer's own ``worktree_path`` against the CALLER's
    ``project_root``/``cwd``, so a unit querying its own identity got
    whichever unit happened to write last — reopening, at tier 0, the exact
    collision round 2's ``per_unit_worktree_identity`` (tier 3) already
    closed. Gated on :func:`per_unit_worktree_identity` rather than running
    unconditionally: a standalone iterate's own worktree is never named
    ``campaign-*--*``, so this never changes behavior outside a campaign
    wave.
    """
    if per_unit_worktree_identity(caller_root) is None:
        return False
    try:
        return Path(pointer_worktree).resolve() != Path(caller_root).resolve()
    except (OSError, ValueError):
        return True


def _in_wave_but_identity_unverifiable(caller_root: Path) -> bool:
    """``True`` when this process is running inside a live wave (the
    ``SHIPWRIGHT_LOOP_UNIT_ID`` sentinel is set — a signal already proven to
    reach a Stop-hook subprocess correctly, since the CI-supplychain-
    authorship-guard has relied on this same env var's truthiness since
    before R5a) but ``caller_root`` cannot be proven to be a genuine
    per-unit worktree. Unlike :func:`_pointer_targets_a_different_wave_unit`
    (which fires once we KNOW the pointer names a sibling), this fires when
    we cannot tell WHOSE pointer it is at all — the shared campaign
    worktree, main, or any other non-per-unit root during a wave.

    External Tier-3 PR review (blocking, R5a): a caller rooted at the shared
    campaign worktree previously fell through to the same session-keyed
    pointer every unit's own ``setup_unit_worktree.py`` call overwrites,
    silently attributing audits/handoffs/triage cards to whichever sibling
    wrote last. Failing closed here — refusing tier 0 outright rather than
    trusting a pointer nothing here can verify is even about THIS caller —
    is deliberately independent of whether ``Path.cwd()`` resolves to the
    per-unit worktree inside a hook subprocess (the still-open "Round 4"
    question the run-id bloat-exception ADR tracks separately): this check
    does not need cwd to resolve correctly for a PER-UNIT caller to be safe,
    only for a NON-per-unit caller to correctly identify itself as such,
    which the sentinel env var already does independent of cwd.
    """
    if not is_wave_sentinel(os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID")):
        return False
    return per_unit_worktree_identity(caller_root) is None

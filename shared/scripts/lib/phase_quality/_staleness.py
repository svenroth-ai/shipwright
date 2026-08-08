"""Provisional-finding staleness check for :func:`_findings.already_audited`.

Split out of ``_findings.py`` (bloat baseline) rather than grown in place —
same one-way reasoning as the earlier ``_run_id`` / ``_iterate_run_id``
splits: this is the one seam in the generic finding schema that needs to ask
an iterate-specific question ("has the run's own ledger entry appeared
since?"), so it gets its own file instead of pulling that question into the
schema module every other phase's findings pass through too.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ._constants import CATEGORIES, REASON_CODE_UNRESOLVABLE_RUN_ID


def is_stale_unresolvable_run_id_finding(
    payload: object, project_root: Path, run_id: str,
) -> bool:
    """True when ``payload`` carries a provisional unresolvable-run-id SKIP
    AND the run's own ``iterate_history`` entry has since appeared.

    A finding tagged ``reason_code=REASON_CODE_UNRESOLVABLE_RUN_ID`` (written
    by ``unresolvable_run_id_skip`` for S2/S3/W2/S9/S10) recorded its verdict
    before the run's own ledger entry existed. Once
    :func:`has_exact_iterate_entry` turns True, that recorded SKIP is stale —
    the checks that deferred to it can now evaluate for real.

    Deferred import: ``tools.verifiers`` is the iterate-specific consumer
    layered ABOVE ``lib.phase_quality`` (every phase's findings pass through
    this module, not just iterate's) — importing it at module level would
    invert that direction. Guarded end-to-end (marker scan, import, and the
    call): this runs inside the Stop hook's per-phase ``try``, but a raise
    here does not merely no-op — it reaches ``write_error_finding``, which
    OVERWRITES the phase's existing finding with an empty-categories error
    payload, destroying a real recorded verdict forever. A malformed finding
    (a hand-edited or corrupted category holding a truthy non-list, e.g.
    ``"canon": 1``) or a broken transitive import
    (``has_exact_iterate_entry``'s own deferred ``lib.iterate_entry`` import,
    which is outside ITS OWN try) would otherwise raise past this point, so
    the whole body falls back to "not stale" (pre-fix behaviour: the SKIP
    stands) on any exception — matching ``has_exact_iterate_entry``'s own
    fail-safe posture — rather than propagating.
    """
    if not isinstance(payload, dict):
        return False
    try:
        has_marker = any(
            isinstance(item, dict) and item.get("reason_code") == REASON_CODE_UNRESOLVABLE_RUN_ID
            for category in CATEGORIES
            for item in (payload.get(category) or [])
        )
        if not has_marker:
            return False
        from tools.verifiers._iterate_run_id import has_exact_iterate_entry
        return has_exact_iterate_entry(project_root, run_id)
    except Exception as exc:  # noqa: BLE001 — see docstring: never destroy a recorded finding
        # A silent fall-back here (doubt-review, delta pass) makes trg-b36fd844
        # a permanent no-op under an import/packaging regression, with every
        # gate still reporting green — the retirement module elsewhere in this
        # same fix always prints on a non-outcome for exactly this reason.
        print(
            f"[phase_quality] is_stale_finding fell back to 'not stale' for "
            f"run_id={run_id!r}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return False


def is_stale_finding(payload: object, project_root: Path, run_id: str) -> bool:
    """True when :func:`_findings.already_audited` should NOT treat
    ``payload`` as final — the single entry point covering both provisional
    shapes the run-id seam made durable (trg-b36fd844) once
    ``(phase, run_id, session_id)`` became stable across a whole run:

    * an ``unresolvable_run_id_skip`` SKIP recorded before the run's own
      ledger entry existed (:func:`is_stale_unresolvable_run_id_finding`).
    * a hook-level error finding — ``write_error_finding``'s empty-categories
      ``source="error"`` payload, the least-informed verdict there is (no
      verdict at all). Without this, a phase whose audit crashed once stays
      frozen at "we don't know" for the rest of the run.
    """
    if isinstance(payload, dict) and payload.get("source") == "error":
        return True
    return is_stale_unresolvable_run_id_finding(payload, project_root, run_id)


__all__ = ["is_stale_finding", "is_stale_unresolvable_run_id_finding"]

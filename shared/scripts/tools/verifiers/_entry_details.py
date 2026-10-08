"""Failure messages shared by the F11 checks that read a block off the F5c entry.

The ledger gate (``_ledger_completeness``) and the surface gate
(``iterate_checks.check_surface_verification``) resolve the run's complexity
from the per-run entry and prefer that entry's copy of their evidence block, so
both fail the same two ways and say so in the same words. Extracted from
``iterate_checks.py`` (at its size cap, ADR-125) together with the ledger check.
"""

from __future__ import annotations

__all__ = ["_no_entry_detail", "_wrong_shape_detail"]


def _wrong_shape_detail(field: str, value: object) -> str:
    """The F5c entry ANSWERED, but not in a shape the gate can read.

    `validate_iterate_entry` performs no shape check on these extra keys, so
    `"test_completeness": "see the spec"` is accepted at F5c and would otherwise
    be silently ignored here — falling through to the shared file and reporting
    "the F5c entry carries no {field} either", which is false and points the
    operator at a repair they already performed (Stage-3 doubt).
    """
    return (
        f"the F5c entry's {field} is a {type(value).__name__}, not an object — "
        "it answered, but not in a shape this gate can read. Fix the "
        "`--entry-json` payload; see references/F5c.md for the block's shape"
    )


def _no_entry_detail(run_id: str) -> str:
    """Why an absent F5c entry FAILS instead of skipping.

    Both gates resolve the run's complexity from the entry; without one they don't
    know what to enforce. SKIPPED there answered "not applicable" to a question
    that was never asked — and at F11, F5c is mandatory and already ran, so an
    absent entry honestly reads "F5c did not happen", never "this run is exempt".
    """
    from tools.append_iterate_entry import ITERATE_RETENTION
    return (
        f"no iterate entry for {run_id} in .shipwright/agent_docs/iterates/ — "
        "this gate cannot resolve the run's complexity and must not report "
        "itself as not-applicable. For the run being finalized this means F5c "
        "did not run: `append_iterate_entry.py --run-id ... --entry-json ...`. "
        f"For an OLDER run it may instead have been evicted by the {ITERATE_RETENTION}-entry "
        "retention window (that directory is a recency cache, not the historical "
        "record — `shipwright_events.jsonl` keeps the `work_completed` event "
        "permanently), in which case the run cannot be re-verified from the "
        "tree and this result is a limit, not a defect"
    )

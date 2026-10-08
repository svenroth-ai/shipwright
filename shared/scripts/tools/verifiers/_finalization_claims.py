"""The registry of "finalization claim" checks - the single extension point.

``iterate_checks.run_all_checks`` holds the historical F11 check list and sits
exactly at its size cap (ADR-125), so a new gate cannot be added to it. Instead
it splices in :func:`run_claim_checks` once, and every later gate that makes
finalization enforce a documented claim registers HERE and keeps its code in
its own ``verifiers/<name>.py``.

To add a gate::

    1. write ``check_<thing>(project_root, run_id, commit_hash="") -> CheckResult``
       in its own verifier module (never in ``iterate_checks.py``);
    2. append it to :data:`CLAIM_CHECKS` (the order is the report order);
    3. add its function name to the "Finalization claim checks" table in
       ``docs/hooks-and-pipeline.md``.

``shared/tests/test_finalization_claims_registry.py`` fails in BOTH directions:
a registered check the docs do not list, and a documented check that is not
registered. The returned list is ``list``-typed on purpose - it is a registry
tests may inspect, not a place for call-time state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .cascade_trigger import check_cascade_trigger
from .common import CheckResult
from .exemption_record_check import check_exemption_record

__all__ = ["CLAIM_CHECKS", "run_claim_checks"]

#: ``(project_root, run_id, commit_hash) -> CheckResult``, in report order.
CLAIM_CHECKS: list[Callable[[Path, str, str], CheckResult]] = [
    check_exemption_record,
    check_cascade_trigger,
]


def run_claim_checks(project_root: Path, run_id: str, commit_hash: str = "") -> list[CheckResult]:
    """Run every registered claim check; one raising check cannot hide the rest."""
    results: list[CheckResult] = []
    for check in CLAIM_CHECKS:
        try:
            results.append(check(project_root, run_id, commit_hash))
        except Exception as exc:  # noqa: BLE001 - a crashed gate must read as RED, not vanish
            results.append(CheckResult(
                getattr(check, "__name__", repr(check)), False,
                f"check crashed: {type(exc).__name__}: {exc}",
            ))
    return results

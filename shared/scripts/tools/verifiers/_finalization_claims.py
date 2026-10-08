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

A registered check module must NEVER import ``iterate_checks``: that module
imports this one at load time, so the import is circular and breaks whichever
side loads first. Shared helpers belong in ``common.py`` or a ``verifiers/_*.py``
module. A check should also expose a module-level ``CHECK_NAME``: a crashed
check is reported under it, so the red row carries the same name a passing run
prints.

``shared/tests/test_finalization_claims_registry.py`` fails in BOTH directions:
a registered check the docs do not list, and a documented check that is not
registered. The returned list is ``list``-typed on purpose - it is a registry
tests may inspect, not a place for call-time state.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from .cascade_trigger import check_cascade_trigger
from .common import CheckResult
from .exemption_record_check import check_exemption_record
from .tag_binding_gate import check_test_tag_binding

__all__ = ["CLAIM_CHECKS", "run_claim_checks"]

#: ``(project_root, run_id, commit_hash) -> CheckResult``, in report order.
CLAIM_CHECKS: list[Callable[[Path, str, str], CheckResult]] = [
    check_exemption_record,
    check_test_tag_binding,
    check_cascade_trigger,
]


def _check_name(check: Callable) -> str:
    """The module's ``CHECK_NAME`` (what a passing run prints), else the function name."""
    module = sys.modules.get(getattr(check, "__module__", "") or "")
    name = getattr(module, "CHECK_NAME", None)
    return name if isinstance(name, str) and name else getattr(check, "__name__", repr(check))


def run_claim_checks(project_root: Path, run_id: str, commit_hash: str = "") -> list[CheckResult]:
    """Run every registered claim check; one raising check cannot hide the rest."""
    results: list[CheckResult] = []
    for check in CLAIM_CHECKS:
        try:
            results.append(check(project_root, run_id, commit_hash))
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - a crashed gate reads RED, never vanishes
            # SystemExit too: a check calling sys.exit() would otherwise end F11 with exit 0 and
            # no report. KeyboardInterrupt (the operator's Ctrl-C) still propagates.
            results.append(CheckResult(_check_name(check), False, f"check crashed: {type(exc).__name__}: {exc}"))
    return results

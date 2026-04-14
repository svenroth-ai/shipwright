"""Modular verifier package for the Shipwright SDLC pipeline.

Iterate 12.0 Foundation (ADR-027) introduces this package as the canonical
home for cross-artifact sync verifiers. Each pipeline phase gets its own
module of `check_*` functions:

- `common.py` — shared ``CheckResult`` dataclass, run_config/events readers,
  generic C1-C5 "Minimum Phase Completion Canon" checks, ADR integrity
  helpers imported from the ``shipwright-check`` plan (Group F).
- `iterate_checks.py` — the 5 existing iterate finalization checks,
  migrated 1:1 from the pre-12.0 ``verify_iterate_finalization.py``.
- `runtime_checks.py` — zombie-task reconciliation stub in 12.0; becomes
  a real event-store / PID-file diff in 12.0b.

Iterate 12.1+ will add `project_checks.py`, `design_checks.py`,
`plan_checks.py`, `build_checks.py`, `test_checks.py`, `changelog_checks.py`,
and `deploy_checks.py`. Compliance does NOT get its own module
(12.5 struck, compliance becomes a detective checker via shipwright-check).

Callers should go through ``verify_phase.py`` (CLI) or import the specific
module they need; this package's ``__init__.py`` re-exports only the stable
``CheckResult`` + ``Severity`` types so downstream code has one import path.
"""

from .common import CheckResult, Severity  # noqa: F401

__all__ = ["CheckResult", "Severity"]

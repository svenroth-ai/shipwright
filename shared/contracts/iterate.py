"""Cross-plugin contract for the iterate complexity classifier.

The iterate plugin (`plugins/shipwright-iterate`) owns the canonical
risk taxonomy and the diff-driven IO-boundary detector. Downstream
consumers (the test plugin's boundary-coverage report, in particular)
used to reach into that implementation via a `_ITERATE_LIB` path
constant + `sys.path.insert(...)`. This module is the supported entry
point that replaces both patterns.

Stable surface
--------------

* :func:`is_io_boundary_change` — diff-driven detector. Returns True
  iff any path in `changed_files` matches the IO-boundary file
  patterns (`.env*`, `hooks.json`, `settings.json`,
  `*_config.json`, `*_state.json`). Used by the test plugin to
  flag iterate specs that touch IO files without declaring an
  `## Affected Boundaries` section.
* :func:`touches_build_files` — companion detector for build-touching
  files (lockfiles + tool configs). Returns True iff any path in
  `changed_files` matches a build-touching pattern.
* :data:`RISK_TAXONOMY` — the canonical dict of risk flags +
  enforcements. Read-only for consumers (downstream readers MUST treat
  the dict as immutable — a future iterate may freeze it via
  `MappingProxyType` if mutation becomes a real bug).
* :data:`IO_BOUNDARY_FILE_PATTERNS` / :data:`TOUCHES_BUILD_FILE_PATTERNS`
  — the regex / glob lists the two detectors consult. Exported so
  consumers can render the detection rules in user-facing reports
  without duplicating them.

**Scope note (reviewer-flagged OpenAI-M1, M12).** This contract pins
ONLY the names the test plugin's `boundary_coverage_report` and
sibling reviewers currently consume. The wider iterate classifier
surface (`classify`, `COMPLEXITY_ORDER`, `estimate_scope`, …) is
intentionally NOT re-exported here — it stays plugin-internal until a
real cross-plugin consumer appears. Adding speculative exports would
inflate the contract surface and lock us into shapes no one needs.

**Backwards compatibility.** Future iterates may split
`plugins/shipwright-iterate/scripts/lib/classify_complexity.py` into
multiple modules. The contract preserves the import names from THIS
file — internal moves stay internal.

Usage::

    from shared.contracts.iterate import is_io_boundary_change

    if is_io_boundary_change(["plugins/foo/hooks/hooks.json"]):
        ...
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Sys.path bootstrap.
#
# `plugins/shipwright-iterate/scripts/lib/classify_complexity.py` has no
# external package dependencies and lives in a flat `scripts/lib/` layout
# (no `__init__.py`). Insert that directory ahead of conflicting `scripts`
# packages from sibling plugins so the import resolves to THIS classifier.
# Anchoring is deterministic on the contract file's own location.
#
# Reviewer-flagged Gemini-H2 / OpenAI-L11: the insert is guarded by a
# `not in sys.path` check so repeated imports do not accumulate paths.
# The idempotence test in `integration-tests/test_shared_contracts_consumers.py`
# (test_iterate_contract_idempotent_import) reload-imports this module
# and asserts `sys.path` is unchanged after the second load.
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
# shared/contracts/iterate.py -> shared/ -> repo_root/
_REPO_ROOT = _THIS_FILE.parent.parent.parent
_ITERATE_LIB = _REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "lib"

if not _ITERATE_LIB.is_dir():  # pragma: no cover — defensive
    raise ImportError(
        "shared.contracts.iterate: could not locate shipwright-iterate plugin "
        f"lib at {_ITERATE_LIB}. Repo layout has changed; the contract must "
        "be updated to match."
    )

_iterate_lib_str = str(_ITERATE_LIB)
if _iterate_lib_str not in sys.path:
    sys.path.insert(0, _iterate_lib_str)


# ---------------------------------------------------------------------------
# Re-exports.
#
# Symbols listed in __all__ are the supported surface. Anything else is
# implementation detail and may move/disappear without notice.
# ---------------------------------------------------------------------------

from classify_complexity import (  # type: ignore[import-not-found]  # noqa: E402, F401
    CI_SUPPLYCHAIN_FILE_PATTERNS,
    CROSS_COMPONENT_FILE_PATTERNS,
    IO_BOUNDARY_FILE_PATTERNS,
    RISK_TAXONOMY,
    TOUCHES_BUILD_FILE_PATTERNS,
    is_ci_supplychain_change,
    is_cross_component_change,
    is_io_boundary_change,
    touches_build_files,
)


__all__ = [
    "CI_SUPPLYCHAIN_FILE_PATTERNS",
    "CROSS_COMPONENT_FILE_PATTERNS",
    "IO_BOUNDARY_FILE_PATTERNS",
    "RISK_TAXONOMY",
    "TOUCHES_BUILD_FILE_PATTERNS",
    "is_ci_supplychain_change",
    "is_cross_component_change",
    "is_io_boundary_change",
    "touches_build_files",
]

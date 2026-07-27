"""Cross-plugin contract for the compliance data collector.

The compliance plugin (`plugins/shipwright-compliance`) owns the
implementation of the unified data collector that walks
`shipwright_events.jsonl`, config files, decision logs, dependency
manifests, and spec files. Downstream consumers (`shipwright-adopt`,
in particular) used to reach into that implementation via subprocess
or ancestor-path-walk. This module is the supported entry point that
replaces both patterns.

Stable surface
--------------

* :func:`collect_all` — primary entry point; collects all compliance
  data for a project root.
* :class:`ComplianceData` — the dataclass returned by `collect_all`.
* :class:`WorkEvent` / :class:`TestRunEvent` / :class:`SplitInfo` /
  :class:`SectionInfo` / :class:`TestResults` / :class:`DecisionEntry`
  / :class:`CommitEntry` / :class:`DependencyInfo` /
  :class:`RequirementInfo` / :class:`KnownFailure` /
  :class:`ExternalReviewState` — the dataclasses `ComplianceData`
  carries. Consumers occasionally need to construct or inspect these
  directly (e.g. adopt seeding fixtures, generator tests).
* :data:`PHASE_REPORTS` — canonical phase → reports table re-exported
  from ``update_compliance.PHASE_REPORTS``. Single source of truth so
  the adopt bridge does not duplicate it.
* :func:`run_report` — `(project_root, data, report_name) -> Path|None`
  invokes the named generator with the canonical signature.
  Encapsulates the ``generate_file`` vs ``generate`` signature
  dispatch so consumers don't reimplement it.

**Backwards compatibility.** Future iterates may split
`plugins/shipwright-compliance/scripts/lib/data_collector.py` into
multiple modules (campaign-B B2). The contract preserves the import
names from THIS file — internal moves stay internal.

Usage::

    from shared.contracts.compliance import collect_all, ComplianceData

    data: ComplianceData = collect_all(project_root)
    print(data.timestamp, len(data.work_events))
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Sys.path bootstrap.
#
# `plugins/shipwright-compliance/scripts/tools/update_compliance.py` itself
# does ``from scripts.lib.data_collector import collect_all`` — i.e. it adds
# the plugin root (parent of ``scripts/``) to sys.path so ``scripts`` is
# importable as a namespace. We replicate that exactly. The bootstrap is
# encapsulated here so consumers never need to know the plugin path layout.
#
# `compliance_bridge.py` historically performed the SAME bootstrap by
# walking ancestors at runtime. With the contract in place, the bootstrap
# happens once at module load, deterministically anchored on this file's
# location.
# ---------------------------------------------------------------------------

_THIS_FILE = Path(__file__).resolve()
# shared/contracts/compliance.py -> shared/ -> repo_root/
_REPO_ROOT = _THIS_FILE.parent.parent.parent
# Resolved, not merely joined: the capture check below compares it against
# `Path(module.__file__).resolve().parents`. If any component were a symlink
# or a Windows junction, an unresolved join would never match and a
# perfectly healthy process would be refused.
_COMPLIANCE_PLUGIN_ROOT = (_REPO_ROOT / "plugins" / "shipwright-compliance").resolve()

if not _COMPLIANCE_PLUGIN_ROOT.is_dir():  # pragma: no cover — defensive
    raise ImportError(
        "shared.contracts.compliance: could not locate shipwright-compliance "
        f"plugin at {_COMPLIANCE_PLUGIN_ROOT}. Repo layout has changed; the "
        "contract must be updated to match."
    )

_plugin_root_str = str(_COMPLIANCE_PLUGIN_ROOT)
if _plugin_root_str not in sys.path:
    sys.path.insert(0, _plugin_root_str)


# ---------------------------------------------------------------------------
# Capture check.
#
# The prepend above is necessary but NOT sufficient, and it is worth being
# precise about why. `scripts` is a namespace package, so its `__path__`
# does re-resolve when sys.path changes. `scripts.lib` and `scripts.tools`
# are NOT: every plugin ships `scripts/lib/__init__.py`, and so does
# `shared/scripts`, which makes them REGULAR packages -- pinned to one
# directory and cached in `sys.modules` on first touch. A regular
# sub-package never re-resolves against sys.path, so once some other tree
# has claimed the name, this contract cannot reach its own modules however
# it reorders sys.path.
#
# That happens most easily under pytest: `shared/tests/__init__.py` exists
# while `shared/__init__.py` does not, so prepend import mode puts
# `<repo>/shared` on sys.path and `shared/scripts` becomes top-level
# `scripts`. A single guarded `from scripts.lib.<x> import ...` in a shared
# test then caches `scripts.lib` -> `shared/scripts/lib` even when that
# import FAILED, and every later consumer of this contract dies on
# `No module named 'scripts.lib.data_collector'` -- an error that names the
# compliance plugin, the one component that is not at fault.
#
# Say so instead. The repo-root conftest refuses multi-root pytest sessions
# up front; this covers every other process, where no conftest runs.
# ---------------------------------------------------------------------------

def _refuse_if_captured() -> None:
    """Raise a NAMED error if this contract's packages are already taken.

    `scripts` itself is checked first. Today every `scripts` directory in
    this repo is a namespace package (no `__init__.py`), so it has
    `__file__ = None` and is skipped -- namespace packages DO re-resolve
    after the prepend and are fine. But if any tree ever gains
    `scripts/__init__.py` it becomes a regular package that pins the
    parent, and the failure would look identical while checks on the
    children stayed silent.

    `scripts.audit` is included because the compliance plugin's audit
    package is also regular, and `update_compliance` imports it lazily at
    call time -- a capture there survives this module's import and only
    detonates later, inside a generator.
    """
    for name in ("scripts", "scripts.lib", "scripts.tools", "scripts.audit"):
        captured = sys.modules.get(name)
        file = getattr(captured, "__file__", None)
        if captured is None or file is None:
            continue
        owner = Path(file).resolve().parent
        if _COMPLIANCE_PLUGIN_ROOT in Path(file).resolve().parents:
            continue
        raise ImportError(
            f"shared.contracts.compliance: `{name}` is already bound to "
            f"{owner}, which is outside the shipwright-compliance plugin at "
            f"{_COMPLIANCE_PLUGIN_ROOT}.\n"
            f"`{name}` is a regular package, so it was cached in sys.modules "
            "on first import and will not re-resolve -- prepending the plugin "
            "root to sys.path (which this module already did) cannot undo it.\n"
            "Cause: another tree in this repo claimed the top-level `scripts` "
            "name earlier in this process. Under pytest that means the session "
            "spans more than one test root; run one root per pytest process "
            "(see the repo-root conftest.py and ADR-044). Otherwise, import "
            "this contract before anything else touches `scripts.*`."
        )


_refuse_if_captured()


# ---------------------------------------------------------------------------
# Re-exports.
#
# Symbols listed in __all__ are the supported surface. Anything else is
# implementation detail and may move/disappear without notice.
# ---------------------------------------------------------------------------

# The targeted noqa: F401 silences the unused-import warning — these names
# ARE used (they're re-exported via __all__), but a plain `import *` would
# pull in private helpers we don't want to publish.
from scripts.lib.data_collector import (  # type: ignore[import-not-found]  # noqa: E402, F401
    ComplianceData,
    CommitEntry,
    DecisionEntry,
    DependencyInfo,
    ExternalReviewState,
    KnownFailure,
    RequirementInfo,
    SectionInfo,
    SplitInfo,
    TestResults,
    TestRunEvent,
    WorkEvent,
    collect_all,
)

# Re-export PHASE_REPORTS + the GENERATORS dispatch from update_compliance.
# Iterate B8 reviewer-flagged (Gemini-H1 / OpenAI-H3): adopt's bridge
# previously duplicated PHASE_REPORTS, creating drift risk. The contract
# is now the single source of truth — both compliance's own CLI and
# adopt's bridge import from here.
from scripts.tools.update_compliance import (  # type: ignore[import-not-found]  # noqa: E402, F401
    GENERATORS,
    PHASE_REPORTS,
)


def run_report(
    project_root: "Path", data: "ComplianceData", report_name: str
) -> "Path | None":
    """Invoke the named generator with the canonical signature.

    Encapsulates the ``generate_file(project_root, data)`` signature
    used by all five core generators (rtm, test_evidence, change_history,
    dashboard, sbom). Returns the output path written by the generator,
    or ``None`` for unknown report names.

    Iterate B8 reviewer-flagged (Gemini-L5 / OpenAI-M10): centralizing
    the dispatch here means consumers never need ``importlib.import_module``
    over user-influenced report names — they pass a string that the
    contract resolves to a static, allowlisted callable.
    """
    gen_fn = GENERATORS.get(report_name)
    if gen_fn is None:
        return None
    return gen_fn(project_root, data)


__all__ = [
    "ComplianceData",
    "CommitEntry",
    "DecisionEntry",
    "DependencyInfo",
    "ExternalReviewState",
    "GENERATORS",
    "KnownFailure",
    "PHASE_REPORTS",
    "RequirementInfo",
    "SectionInfo",
    "SplitInfo",
    "TestResults",
    "TestRunEvent",
    "WorkEvent",
    "collect_all",
    "run_report",
]

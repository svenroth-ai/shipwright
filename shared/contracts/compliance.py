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
_COMPLIANCE_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "shipwright-compliance"

if not _COMPLIANCE_PLUGIN_ROOT.is_dir():  # pragma: no cover — defensive
    raise ImportError(
        "shared.contracts.compliance: could not locate shipwright-compliance "
        f"plugin at {_COMPLIANCE_PLUGIN_ROOT}. Repo layout has changed; the "
        "contract must be updated to match."
    )

# Insert ahead of any conflicting `scripts` packages from sibling plugins.
_plugin_root_str = str(_COMPLIANCE_PLUGIN_ROOT)
if _plugin_root_str not in sys.path:
    sys.path.insert(0, _plugin_root_str)


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

"""Compliance data collectors — public surface.

This package is the new home of what used to live in the 1559-LOC
monolith ``scripts/lib/data_collector.py``. The public symbols below
preserve the pre-split import surface exactly:

* :func:`collect_all` — primary entry; returns ``ComplianceData``.
* The dataclasses (``ComplianceData``, ``SplitInfo``, …) are re-exported
  for downstream consumers (most importantly the
  ``shared.contracts.compliance`` cross-plugin contract).
* The individual ``collect_*`` functions are re-exported so legacy
  callers and tests can still reach them directly.
* The ``EVENT_FILE`` constant + the ``_resolve_events_path`` helper are
  re-exported because the test suite probes them directly.

Iterate Campaign B (B2): split out of ``data_collector.py``.
"""

from __future__ import annotations

from pathlib import Path

from ._common import CONFIG_FILES, collect_configs
from ._license_const import NOT_INSTALLED, UNKNOWN_LICENSE
from ._types import (
    CommitEntry,
    ComplianceData,
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
)
from .change_history import (
    EVENT_FILE,
    _apply_amendments,
    _read_event_log,
    _resolve_events_path,
    collect_events,
    collect_git_history,
    latest_event_timestamp,
)
from .dashboard import (
    _sections_from_data,
    collect_sections,
    collect_splits,
    map_requirements_to_sections,
)
from .rtm import (
    collect_decision_log,
    collect_external_review_states,
    collect_requirements,
    map_requirements_to_events,
)
from .sbom import (
    _collect_dependency_rows,
    collect_dependencies,
    collect_undeclared_by_workspace,
)
from .test_evidence import (
    collect_known_failures,
    collect_test_files,
    collect_test_results,
)
from .test_links import (
    build_manifest as build_test_traceability_manifest,
    generate_file as generate_test_links,
)


def collect_all(project_root: Path) -> ComplianceData:
    """Collect all compliance-relevant data from a project.

    Primary source: shipwright_events.jsonl (if exists).
    Falls back to config files for legacy fields.
    """
    project_root = Path(project_root).resolve()

    # Event-sourced data
    work_events, test_runs, phase_events = collect_events(project_root)

    # Legacy data (still populated for generators not yet migrated)
    sections = collect_sections(project_root)

    requirements = collect_requirements(project_root)
    # Map requirements: prefer event-based mapping if events exist
    if work_events:
        map_requirements_to_events(requirements, work_events)
    else:
        map_requirements_to_sections(requirements, sections)

    known_failures, baseline_count = collect_known_failures(project_root)

    # SBOM inventory + render metadata in one pass (AR-04): dedup-merge count
    # and whether any version was resolved from a uv.lock.
    dependencies, deps_deduped, deps_lock_resolved = _collect_dependency_rows(project_root)

    return ComplianceData(
        project_root=project_root,
        # Event-sourced
        work_events=work_events,
        test_runs=test_runs,
        phase_events=phase_events,
        # Legacy
        configs=collect_configs(project_root),
        splits=collect_splits(project_root),
        sections=sections,
        test_results=collect_test_results(project_root),
        # Shared
        decisions=collect_decision_log(project_root),
        commits=collect_git_history(project_root),
        dependencies=dependencies,
        dependencies_deduped=deps_deduped,
        dependencies_lock_resolved=deps_lock_resolved,
        requirements=requirements,
        test_file_map=collect_test_files(project_root),
        external_review_states=collect_external_review_states(project_root),
        # Known failures
        known_failures=known_failures,
        baseline_failure_count=baseline_count,
        # Deterministic banner — see iterate-2026-05-22-deterministic-render-timestamps.
        # Using `datetime.now()` here made every compliance generator's
        # `Generated: ...` header drift on every call, leaving the rendered
        # `.shipwright/compliance/*.md` permanently dirty in `git status`.
        # Pin to the most recent event's timestamp so two runs against the
        # same events.jsonl produce byte-identical output. Falls back to a
        # stable literal when no events have been recorded yet.
        timestamp=latest_event_timestamp(work_events),
    )


__all__ = [
    # Dataclasses
    "CommitEntry",
    "ComplianceData",
    "DecisionEntry",
    "DependencyInfo",
    "ExternalReviewState",
    "KnownFailure",
    "RequirementInfo",
    "SectionInfo",
    "SplitInfo",
    "TestResults",
    "TestRunEvent",
    "WorkEvent",
    # Constants
    "CONFIG_FILES",
    "EVENT_FILE",
    "NOT_INSTALLED",
    "UNKNOWN_LICENSE",
    # Top-level entry
    "collect_all",
    # Traceability manifest (campaign TT1)
    "build_test_traceability_manifest",
    "generate_test_links",
    # Collectors
    "collect_configs",
    "collect_dependencies",
    "collect_decision_log",
    "collect_events",
    "collect_external_review_states",
    "collect_git_history",
    "collect_known_failures",
    "collect_requirements",
    "collect_sections",
    "collect_splits",
    "collect_test_files",
    "collect_test_results",
    "collect_undeclared_by_workspace",
    "latest_event_timestamp",
    # Helpers re-exported for backwards compat (test imports)
    "_apply_amendments",
    "_read_event_log",
    "_resolve_events_path",
    "_sections_from_data",
    "map_requirements_to_events",
    "map_requirements_to_sections",
]

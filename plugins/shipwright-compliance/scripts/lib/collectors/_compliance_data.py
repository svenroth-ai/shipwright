"""The aggregate every compliance renderer is handed.

Split out of ``_types.py`` (which keeps the leaf value types) when the
provenance header grew its third field and pushed that module past its 300-line
budget. The two are different things and change for different reasons: a leaf
type changes when one artifact's shape changes; this aggregate changes whenever
a *new fact* has to reach the renderers — which is exactly what keeps happening
(``timestamp``, then ``run_id``, then ``audit_freshness_note``, from three
separate cards). Giving it its own module means the next such fact costs a line
here instead of another budget fight in ``_types``.

Collect-once / render-many: ``collectors.collect_all`` is the single production
constructor. Directly-constructed instances (tests, fixtures) get the field
defaults, which are chosen so a renderer degrades to its pre-feature output
rather than to a false claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ._types import (
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
)


@dataclass
class ComplianceData:
    project_root: Path
    # Event-sourced (primary)
    work_events: list[WorkEvent] = field(default_factory=list)
    test_runs: list[TestRunEvent] = field(default_factory=list)
    phase_events: list[dict] = field(default_factory=list)
    # Legacy (still populated for backward compat during migration)
    configs: dict[str, dict] = field(default_factory=dict)
    splits: list[SplitInfo] = field(default_factory=list)
    sections: list[SectionInfo] = field(default_factory=list)
    test_results: TestResults | None = None
    # Shared (unchanged sources)
    decisions: list[DecisionEntry] = field(default_factory=list)
    commits: list[CommitEntry] = field(default_factory=list)
    dependencies: list[DependencyInfo] = field(default_factory=list)
    # SBOM render metadata (AR-04); legacy ctors keep 0/False.
    dependencies_deduped: int = 0
    dependencies_lock_resolved: bool = False
    requirements: list[RequirementInfo] = field(default_factory=list)
    test_file_map: dict[str, list[str]] = field(default_factory=dict)
    external_review_states: list[ExternalReviewState] = field(default_factory=list)
    # Known / baseline failures
    known_failures: list[KnownFailure] = field(default_factory=list)
    baseline_failure_count: int = 0
    # --- Provenance header (rendered as a block by lib/_provenance.py) ---
    #: When the document was written — pinned to an event, never the clock.
    timestamp: str = ""
    #: Run id off the SAME event as ``timestamp``, so the two cannot disagree.
    run_id: str | None = None
    #: Whether anything ever cross-checked that state — see lib/audit_disclosure.
    audit_freshness_note: str = ""


__all__ = ["ComplianceData"]

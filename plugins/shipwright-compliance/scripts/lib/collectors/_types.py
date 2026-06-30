"""Public dataclass surface for the compliance collectors package.

Single owner of the dataclass definitions imported by every collector module
and re-exported by ``collectors/__init__.py``; ``_common.py`` carries the
shared runtime helpers (config-file readers).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SplitInfo:
    name: str
    status: str  # "complete" | "in_progress" | "pending"
    spec_path: str | None = None


@dataclass
class SectionInfo:
    name: str
    split: str
    status: str
    commit: str | None = None
    tests_passed: int = 0
    tests_total: int = 0
    review_findings: int = 0
    review_findings_fixed: int = 0
    review_type: str = ""  # "self-review" | "full-review" | "" (unknown)
    estimated_tokens: int = 0
    estimated_api_calls: int = 0


@dataclass
class DecisionEntry:
    section: str
    timestamp: str
    commit: str = ""
    decisions: list[dict] = field(default_factory=list)
    # Each dict: {"decision": str, "context": str, "consequences": str, "rejected": str}


@dataclass
class CommitEntry:
    hash: str
    type: str
    scope: str | None
    description: str
    date: str
    author: str


@dataclass
class DependencyInfo:
    name: str
    version: str
    dep_type: str  # "runtime" | "dev"
    license: str = "unknown"


@dataclass
class TestResults:
    """Aggregated test results from test phase (shipwright_test_results.json)."""
    status: str = ""  # "pass" | "fail"
    timestamp: str = ""
    schema_version: int = 1  # 1 = legacy (no integration), 2 = with integration/pgtap
    unit_passed: int = 0
    unit_total: int = 0
    unit_duration_s: float = 0
    integration_passed: int = 0
    integration_total: int = 0
    integration_duration_s: float = 0
    integration_skipped: bool = False
    integration_skip_reason: str = ""
    pgtap_passed: int = 0
    pgtap_total: int = 0
    pgtap_duration_s: float = 0
    pgtap_skipped: bool = False
    pgtap_skip_reason: str = ""
    smoke_status: str = ""  # "pass" | "fail" | "skip" | "skipped"
    smoke_url: str = ""
    smoke_response_ms: int = 0
    e2e_passed: int = 0
    e2e_total: int = 0
    e2e_failures: list[str] = field(default_factory=list)
    e2e_skipped: bool = False
    e2e_skip_reason: str = ""
    design_fidelity_passed: int = 0
    design_fidelity_total: int = 0
    design_fidelity_skipped: bool = False
    design_fidelity_skip_reason: str = ""
    design_fidelity_report_path: str = ""  # Path to design-fidelity-report.json if available
    consistency_passed: int = 0
    consistency_total: int = 0
    consistency_skipped: bool = False
    consistency_skip_reason: str = ""


@dataclass
class RequirementInfo:
    """A functional requirement parsed from spec.md."""
    id: str           # "FR-02.01"
    text: str         # "The system SHALL..."
    priority: str     # "Must" | "Should" | "May"
    split: str        # "02-course-platform"
    spec_path: str = ""  # Relative path to spec.md
    sections: list[str] = field(default_factory=list)


@dataclass
class KnownFailure:
    """A known pre-existing test failure."""
    test: str
    description: str = ""
    ticket: str = ""
    added: str = ""
    count: int = 1


@dataclass
class WorkEvent:
    """Unified representation of any work_completed event (build or iterate)."""
    id: str
    timestamp: str
    source: str          # "build" | "iterate"
    commit: str = ""
    tests_passed: int = 0
    tests_total: int = 0
    affected_frs: list[str] = field(default_factory=list)
    # Build-specific
    split: str = ""
    section: str = ""
    review_type: str = ""
    review_findings: int = 0
    review_fixed: int = 0
    # Iterate-specific
    intent: str = ""     # "feature" | "change" | "bug"
    description: str = ""
    new_frs: list[str] = field(default_factory=list)
    tests_new: int = 0
    tests_modified: int = 0
    e2e_run: bool = False
    spec_updated: str = ""
    adr_id: str = ""
    # FR-classification (BP-1): FR-linked vs satisfied-no-FR change; legacy -> "".
    change_type: str = ""
    none_reason: str = ""
    spec_impact: str = ""
    # BP-2: per-FR behavior impact {FR-id: add|modify|remove|none}; legacy → {}.
    fr_impact: dict[str, str] = field(default_factory=dict)
    summary: str = ""  # plain-language one-liner (forward-only); preferred in the Event column

    @classmethod
    def from_dict(cls, d: dict) -> WorkEvent:
        # `or {}`/`or []` (not a `.get` default) so an EXPLICIT `null` coerces like a missing key.
        tests = d.get("tests") or {}
        review = d.get("review") or {}
        return cls(
            id=d.get("id", ""),
            timestamp=d.get("ts", ""),
            source=d.get("source", ""),
            commit=d.get("commit", ""),
            tests_passed=tests.get("passed", 0),
            tests_total=tests.get("total", 0),
            affected_frs=d.get("affected_frs") or [],
            split=d.get("split", ""),
            section=d.get("section", ""),
            review_type=review.get("type", ""),
            review_findings=review.get("findings", 0),
            review_fixed=review.get("fixed", 0),
            intent=d.get("intent", ""),
            description=d.get("description", ""),
            new_frs=d.get("new_frs") or [],
            tests_new=tests.get("new", 0),
            tests_modified=tests.get("modified", 0),
            e2e_run=tests.get("e2e_run", False),
            spec_updated=d.get("spec_updated", ""),
            adr_id=d.get("adr_id", ""),
            change_type=d.get("change_type") or "",
            none_reason=d.get("none_reason") or "",
            spec_impact=d.get("spec_impact") or "",
            summary=d.get("summary", ""),
            fr_impact={k: v.strip().lower() for k, v in (d.get("fr_impact") or {}).items()
                       if isinstance(k, str) and isinstance(v, str)}
            if isinstance(d.get("fr_impact"), dict) else {},
        )


@dataclass
class TestRunEvent:
    """Full test suite execution from event log.

    The ``layers`` dict carries ``unit`` / ``integration`` / ``pgtap`` /
    ``e2e`` / ``smoke`` keys, each with an optional ``failed`` count (readers
    fall back to ``total - passed``). Missing keys read as zero so historical
    runs never crash. ``*_evaluated`` flags whether a layer was reported AT ALL
    — "omitted" (unknown) vs "ran with zero tests" (configured but empty).
    """
    id: str
    timestamp: str
    trigger: str = ""
    unit_passed: int = 0
    unit_total: int = 0
    unit_failed: int | None = None
    unit_evaluated: bool = False
    integration_passed: int = 0
    integration_total: int = 0
    integration_failed: int | None = None
    integration_evaluated: bool = False
    pgtap_passed: int = 0
    pgtap_total: int = 0
    pgtap_failed: int | None = None
    pgtap_evaluated: bool = False
    e2e_passed: int = 0
    e2e_total: int = 0
    e2e_failed: int | None = None
    e2e_evaluated: bool = False
    smoke_status: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> TestRunEvent:
        # Reviewer-flagged Gemini-L4: a malformed event with `layers: null`
        # (not missing — explicitly null) would crash `.get(name, {})`.
        # Use `or {}` so both missing and null collapse to empty dict.
        layers = d.get("layers") or {}
        unit = layers.get("unit") or {}
        integration = layers.get("integration") or {}
        pgtap = layers.get("pgtap") or {}
        e2e = layers.get("e2e") or {}
        smoke = layers.get("smoke") or {}
        return cls(
            id=d.get("id", ""),
            timestamp=d.get("ts", ""),
            trigger=d.get("trigger", ""),
            unit_passed=unit.get("passed", 0),
            unit_total=unit.get("total", 0),
            unit_failed=unit.get("failed") if "failed" in unit else None,
            unit_evaluated=bool(unit),
            integration_passed=integration.get("passed", 0),
            integration_total=integration.get("total", 0),
            integration_failed=integration.get("failed") if "failed" in integration else None,
            integration_evaluated=bool(integration),
            pgtap_passed=pgtap.get("passed", 0),
            pgtap_total=pgtap.get("total", 0),
            pgtap_failed=pgtap.get("failed") if "failed" in pgtap else None,
            pgtap_evaluated=bool(pgtap),
            e2e_passed=e2e.get("passed", 0),
            e2e_total=e2e.get("total", 0),
            e2e_failed=e2e.get("failed") if "failed" in e2e else None,
            e2e_evaluated=bool(e2e),
            smoke_status=smoke.get("status", ""),
        )


@dataclass
class ExternalReviewState:
    """External LLM review outcome for a planning split.

    Written by shipwright-plan Step 5 (v0.3.0+) — either after running the
    external review or after the user opted into the self-review fallback.
    Provides audit evidence that the quality gate was considered even when
    external review did not run.
    """
    split: str
    status: str                   # completed | skipped_user_opt_out | skipped_config_disabled | missing
    provider: str | None = None   # openrouter | gemini | openai | null
    findings_count: int = 0
    self_review_fallback_ran: bool = False
    reason: str | None = None
    timestamp: str = ""


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
    timestamp: str = ""

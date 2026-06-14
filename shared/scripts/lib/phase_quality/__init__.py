"""Phase-Quality-Audit infrastructure.

Finding-JSON schema, atomic writes, aggregate rewrites, dashboard
regeneration and helpers for the Stop-hook consolidated audit entry
point (``shared/scripts/hooks/audit_phase_quality_on_stop.py``).

This package replaces the 1108-LOC monolithic
``shared/scripts/lib/phase_quality.py`` that lived here before Iterate
Campaign B (B3). The public import surface is preserved 1:1 — every
symbol exported from the pre-split ``phase_quality.py`` is re-exported
here, so existing callers (the audit Stop hook, test_audit_phase_quality,
test_phase_quality_rollout, every ``tools/verifiers/*_compliance.py``)
work unchanged.

Submodule layout:

* :mod:`._constants` — phase maps, category sets, paths, status strings.
* :mod:`._flags` — ``SHIPWRIGHT_*`` env-flag readers.
* :mod:`._resolution` — project / phase / run-id / source resolution.
* :mod:`._findings` — finding-dict schema + atomic JSON writer.
* :mod:`._runners` — canon / workflow / infra / trace / quality / spec
  category runners.
* :mod:`._aggregates` — finding loading + GC + locked aggregate driver.
* :mod:`._dashboard_render` — Markdown renderers for the three
  skill-compliance dashboards.
* :mod:`._bloat_findings` — bloat-baseline summary for the project-wide
  Compliance Dashboard.

Design rules:

- Never block: every public function is best-effort; callers exit 0.
- Deterministic regeneration: dashboard + aggregate report are rewritten
  from per-run finding JSON files, not mutated in place.
- Cross-platform locks via ``shared/scripts/lib/file_lock.py``.
- Greenfield-safe: ``is_shipwright_project`` gates the whole pipeline,
  so running this in a non-Shipwright repo is a silent no-op.
"""

from __future__ import annotations

from ._aggregates import (
    LoadedFinding,
    count_by_status,
    gc_old_findings,
    load_actionable_findings,
    load_findings,
    regenerate_all_aggregates,
)
from ._bloat_findings import collect_bloat_summary
from ._constants import (
    C4_PHASES,
    C5_CATEGORY,
    C5_PHASES,
    CATEGORIES,
    DASHBOARD_PATH,
    FINDING_DIR,
    GC_AGE_DAYS,
    LOCK_PATH,
    MAX_REPORT_RUNS,
    MAX_SESSION_SUMMARY_RUNS,
    PLUGIN_TO_PHASE,
    REPORT_PATH,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    SUMMARY_PATH,
    TIER_2_CHECK_IDS,
    is_sentinel_run,
)
from ._dashboard_render import (
    rewrite_aggregated_report,
    rewrite_session_findings_summary,
    write_quality_dashboard_file,
)
from ._findings import (
    already_audited,
    apply_skip_override,
    finding_path,
    make_finding,
    write_error_finding,
    write_finding_json,
)
from ._flags import (
    flag_enabled,
    override_reason,
    phase_quality_enabled,
    skipped_check_ids,
)
from ._resolution import (
    cwd_is_strict_ancestor_of,
    is_shipwright_project,
    phase_from_plugin_root,
    project_root_was_explicitly_selected,
    resolve_engaged_phases,
    resolve_run_id,
    resolve_source,
)
from ._runners import (
    run_canon_checks,
    run_infrastructure_checks,
    run_quality_checks,
    run_spec_checks,
    run_traceability_checks,
    run_workflow_checks,
)
from ._triage_bundle import (
    BACKLOG_PREFIX,
    DASHBOARD_REL,
    collect_in_scope_fails,
    emit_phase_quality_backlog,
    load_engagement_inputs,
    phase_is_engaged,
)


__all__ = [
    "C4_PHASES",
    "C5_PHASES",
    "C5_CATEGORY",
    "CATEGORIES",
    "DASHBOARD_PATH",
    "FINDING_DIR",
    "GC_AGE_DAYS",
    "LOCK_PATH",
    "MAX_REPORT_RUNS",
    "MAX_SESSION_SUMMARY_RUNS",
    "PLUGIN_TO_PHASE",
    "REPORT_PATH",
    "STATUS_FAIL",
    "STATUS_PASS",
    "STATUS_SKIP",
    "STATUS_WARN",
    "SUMMARY_PATH",
    "TIER_2_CHECK_IDS",
    "BACKLOG_PREFIX",
    "DASHBOARD_REL",
    "LoadedFinding",
    "already_audited",
    "apply_skip_override",
    "collect_bloat_summary",
    "collect_in_scope_fails",
    "count_by_status",
    "emit_phase_quality_backlog",
    "load_engagement_inputs",
    "phase_is_engaged",
    "resolve_engaged_phases",
    "cwd_is_strict_ancestor_of",
    "finding_path",
    "flag_enabled",
    "gc_old_findings",
    "is_sentinel_run",
    "is_shipwright_project",
    "load_actionable_findings",
    "load_findings",
    "make_finding",
    "override_reason",
    "phase_from_plugin_root",
    "phase_quality_enabled",
    "project_root_was_explicitly_selected",
    "regenerate_all_aggregates",
    "resolve_run_id",
    "resolve_source",
    "rewrite_aggregated_report",
    "rewrite_session_findings_summary",
    "run_canon_checks",
    "run_infrastructure_checks",
    "run_quality_checks",
    "run_spec_checks",
    "run_traceability_checks",
    "run_workflow_checks",
    "skipped_check_ids",
    "write_error_finding",
    "write_finding_json",
    "write_quality_dashboard_file",
]

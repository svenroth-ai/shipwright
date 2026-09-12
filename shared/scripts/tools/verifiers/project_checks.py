"""Project-phase verifier checks.

Iterate 12.1 brings the ``project`` plugin to full Minimum Phase
Completion Canon coverage. Before 12.1 the plugin had C1 (record_event),
C2 (update_build_dashboard) and C4 (write_decision_log) but was missing
C3 (inline session_handoff) and C5 (CHANGELOG [Unreleased] entry). The
SKILL.md step 8 patch in 12.1 adds both of those; this module verifies
that every canon step actually ran, plus phase-own invariants
(project_config status, manifest-vs-dirs alignment) and ADR integrity
(F1/F2/F3 from the shipwright-check plan).

P4.2 adds the grill-trace completeness gate (``check_grill_trace_completeness``)
as a phase-own check. Its Step-8 prose companion
(``step-8-completion.md`` item 7) told the agent to run
``verify_grill_trace_completeness.py`` and decide for itself whether to
stop — a REJECTed spec-reviewer round found that "not just advisory" (the
sub-iterate spec's own AC2 wording) cannot be satisfied by an
LLM-followed instruction alone, so it is registered here too: the same
code-level dispatcher C1-C5 already use to genuinely block
``update-step --step project`` via ``phase_validators._run_canon_checks``.

Severity strategy:

- Phase-own ``project_config_status_complete`` → ERROR (blocks next phase)
- Phase-own ``manifest_splits_match_dirs`` → WARNING (cosmetic drift)
- Phase-own ``check_grill_trace_completeness`` → ERROR for every hard
  STOP (severities are those ``verify_grill_trace_completeness.py``'s own
  ``CheckResult``s already carry — unchanged, not re-classified here)
- C1/C4/C5 → ERROR (required artifacts)
- C2/C3 → WARNING (advisory but visible)
- Phase history (``run_id`` match) → ERROR only when a run id was given
- ADR integrity (F1/F2/F3) → ERROR (phase-agnostic but cheap to run
  per phase so every phase completion re-validates the global invariant)
"""

from __future__ import annotations

from pathlib import Path

from . import _project_gate_wiring as _gate_wiring
from .common import (
    CheckResult,
    Severity,
    check_adr_ids_sequential,
    check_adr_status_valid,
    check_adr_supersession_exists,
    check_c1_phase_event_recorded,
    check_c2_dashboard_reflects_phase,
    check_c4_decision_log_has_phase_adr,
    check_c5_changelog_unreleased_has_phase_entry,
    check_phase_history_has_run,
    read_run_config,
)
from .handoff_phase_canon import check_c3_session_handoff_fresh_after_phase



# Canonical home of the planning artifact set, relative to project_root.
# Mirrors PLANNING_DIR in shared/scripts/lib/artifact_migrations.py.
PLANNING_DIRNAME = ".shipwright/planning"

# ---------------------------------------------------------------------------
# Phase-own checks
# ---------------------------------------------------------------------------

def check_project_config_status_complete(project_root: Path) -> CheckResult:
    """The project plugin writes ``shipwright_project_config.json``
    with ``status: complete`` when Step 8 marks the phase done. If the
    file is missing or the status is still ``in_progress``, the project
    phase is not actually complete.
    """
    name = "project_config status=complete"
    path = project_root / "shipwright_project_config.json"
    if not path.exists():
        return CheckResult(name, False, "shipwright_project_config.json missing")
    try:
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(name, False, f"malformed project config: {exc}")
    status = data.get("status")
    if status != "complete":
        return CheckResult(name, False, f"status={status!r}, expected 'complete'")
    return CheckResult(name, True, "status=complete")


def check_manifest_splits_match_dirs(project_root: Path) -> CheckResult:
    """Every split in ``shipwright_project_config.json::splits`` should
    have a matching ``.shipwright/planning/<name>/`` directory on disk, and vice
    versa. Drift here means the spec generation / directory creation
    got out of sync. WARNING severity — the mismatch is cosmetic until
    a downstream plugin tries to read a missing spec.md.
    """
    name = "project manifest splits match planning dirs"
    data = read_run_config(project_root)  # permissive reader; returns {} on missing
    # Fall back to project_config if run_config has no splits (project
    # plugin writes to shipwright_project_config.json, not run_config).
    path = project_root / "shipwright_project_config.json"
    if path.exists():
        import json
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    splits = data.get("splits") or []
    declared = {s.get("name") for s in splits if isinstance(s, dict) and s.get("name")}

    planning_dir = project_root / PLANNING_DIRNAME
    if not planning_dir.is_dir():
        if declared:
            return CheckResult(
                name,
                False,
                f".shipwright/planning/ missing but config declares {len(declared)} split(s)",
                severity=Severity.WARNING.value,
            )
        return CheckResult(name, True, "no splits declared, no .shipwright/planning/ dir — consistent")

    present = {
        p.name for p in planning_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name != "iterate"
    }

    missing = sorted(declared - present)
    extra = sorted(present - declared)
    if missing and extra:
        return CheckResult(
            name, False,
            f"missing dirs: {missing}, extra dirs: {extra}",
            severity=Severity.WARNING.value,
        )
    if missing:
        return CheckResult(
            name, False,
            f"declared splits without .shipwright/planning/<name>/ dir: {missing}",
            severity=Severity.WARNING.value,
        )
    if extra:
        return CheckResult(
            name, False,
            f".shipwright/planning/ dirs without declared split: {extra}",
            severity=Severity.WARNING.value,
        )
    return CheckResult(name, True, f"{len(declared)} split(s) match .shipwright/planning/ layout")


def check_grill_trace_completeness(project_root: Path) -> list[CheckResult]:
    """P4.2 — the grill-trace completeness gate, wired as a genuine
    code-level block (not the Step-8 prose that preceded it).

    Delegates to ``verify_grill_trace_completeness.run_all_checks`` — the
    single source of truth for the four closed-vocabulary STOP conditions
    (blank dimension, greenfield ``assumed``, undefined term, outcome
    without fit_criterion) plus its structural guards
    (``grill_trace_coverage``, ``fr_trace_coverage``,
    ``glossary_source_available``, ``glossary_delta_declared``,
    ``malformed_trace``) — and returns its ``CheckResult`` list UNCHANGED:
    same names, same detail text (which names the specific failing
    trace/dimension/term), same severities. ``run_project_checks`` below
    extends its own flat result list with these rather than wrapping them
    in one summary result, so a red result still names the exact gap the
    way the standalone CLI already does, and ``_run_canon_checks``
    (``phase_validators.py``) turns each ERROR-severity one into a genuine
    ask-level, ``update-step``-blocking issue — the same path C1-C5 use.

    A raised exception from the delegate (never expected — the delegate's
    own ``run_all_checks`` already turns a malformed trace into a
    ``malformed_trace`` CheckResult instead of raising) is still caught
    here so a bug in the gate blocks the phase with a visible message
    instead of crashing ``update-step`` outright.
    """
    from tools.verify_grill_trace_completeness import run_all_checks as _run_grill_checks
    try:
        return _run_grill_checks(project_root)
    except Exception as exc:  # noqa: BLE001 — surface, don't crash update-step
        return [CheckResult(
            "grill_trace_completeness",
            False,
            f"verify_grill_trace_completeness.run_all_checks raised "
            f"{type(exc).__name__}: {exc}",
        )]


# ---------------------------------------------------------------------------
# Canon dispatcher (C1-C5 + phase history + ADR integrity)
# ---------------------------------------------------------------------------

def run_project_checks(
    project_root: Path,
    *,
    run_id: str = "",
) -> list[CheckResult]:
    """Run the full project-phase verifier suite in stable order.

    The order mirrors what a human reviewer would check: phase-own
    artifacts first (is the project actually "done"?), then canon
    steps (did every finalization tool run?), then phase-history and
    ADR integrity (cross-phase invariants that every run re-validates).
    """
    results: list[CheckResult] = []

    # Phase-own
    results.append(check_project_config_status_complete(project_root))
    results.append(check_manifest_splits_match_dirs(project_root))
    results.extend(check_grill_trace_completeness(project_root))

    # FR-01.02 #4/#15, #5, #10, #11 (req3-06-enforcement-mono sub-iterate e2)
    results.append(_gate_wiring.check_basis_forbids_assumed(project_root))
    results.append(_gate_wiring.check_criteria_free_of_implementation_detail(project_root))
    results.append(_gate_wiring.check_no_empty_split(project_root))
    results.append(_gate_wiring.check_starting_guidance_present(project_root))

    # Canon (generic helpers from common.py)
    results.append(check_c1_phase_event_recorded(project_root, "project"))
    results.append(check_c2_dashboard_reflects_phase(project_root, "project"))
    results.append(check_c3_session_handoff_fresh_after_phase(project_root, "project"))
    results.append(check_c4_decision_log_has_phase_adr(project_root, "project"))
    results.append(check_c5_changelog_unreleased_has_phase_entry(project_root, "project", "Added"))

    # Phase history
    results.append(check_phase_history_has_run(project_root, "project", run_id))

    # ADR integrity (phase-agnostic but cheap; fail-fast on drift)
    results.append(check_adr_ids_sequential(project_root))
    results.append(check_adr_status_valid(project_root))
    results.append(check_adr_supersession_exists(project_root))

    return results


def run_all_checks(project_root: Path, run_id: str = "") -> list[CheckResult]:
    """Alias kept for symmetry with ``iterate_checks``."""
    return run_project_checks(project_root, run_id=run_id)

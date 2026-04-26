"""Project-phase verifier checks.

Iterate 12.1 brings the ``project`` plugin to full Minimum Phase
Completion Canon coverage. Before 12.1 the plugin had C1 (record_event),
C2 (update_build_dashboard) and C4 (write_decision_log) but was missing
C3 (inline session_handoff) and C5 (CHANGELOG [Unreleased] entry). The
SKILL.md step 8 patch in 12.1 adds both of those; this module verifies
that every canon step actually ran, plus phase-own invariants
(project_config status, manifest-vs-dirs alignment) and ADR integrity
(F1/F2/F3 from the shipwright-check plan).

Severity strategy:

- Phase-own ``project_config_status_complete`` → ERROR (blocks next phase)
- Phase-own ``manifest_splits_match_dirs`` → WARNING (cosmetic drift)
- C1/C4/C5 → ERROR (required artifacts)
- C2/C3 → WARNING (advisory but visible)
- Phase history (``run_id`` match) → ERROR only when a run id was given
- ADR integrity (F1/F2/F3) → ERROR (phase-agnostic but cheap to run
  per phase so every phase completion re-validates the global invariant)
"""

from __future__ import annotations

from pathlib import Path

from .common import (
    CheckResult,
    Severity,
    check_adr_ids_sequential,
    check_adr_status_valid,
    check_adr_supersession_exists,
    check_c1_phase_event_recorded,
    check_c2_dashboard_reflects_phase,
    check_c3_session_handoff_fresh_after_phase,
    check_c4_decision_log_has_phase_adr,
    check_c5_changelog_unreleased_has_phase_entry,
    check_phase_history_has_run,
    read_run_config,
)



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
    """Alias kept for symmetry with ``iterate_checks`` / ``runtime_checks``."""
    return run_project_checks(project_root, run_id=run_id)

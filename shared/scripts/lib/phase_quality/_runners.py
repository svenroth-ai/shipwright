"""Category runners — Canon (C1-C5) + Workflow + Infra + Trace + Quality + Spec.

Top-level dispatchers. The Canon checks (C1-C5) are run directly here
against ``tools/verifiers/common.py`` helpers; every other category
lazy-imports the per-phase wrapper from ``tools/verifiers/`` and
converts internal failures into a single error-finding so the Stop hook
stays non-blocking (plan § 5.5).

Iterate Campaign B (B3): split out of the 1108-LOC monolith.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from tools.verifiers.common import (  # noqa: E402
    CheckResult,
    Severity,
    check_c1_phase_event_recorded,
    check_c2_dashboard_reflects_phase,
    check_c3_session_handoff_fresh_after_phase,
    check_c4_decision_log_has_phase_adr,
    check_c5_changelog_unreleased_has_phase_entry,
)

from ._constants import C4_PHASES, C5_CATEGORY, C5_PHASES, STATUS_FAIL, STATUS_SKIP
from ._findings import _check_result_to_finding, apply_skip_override
from ._flags import override_reason, skipped_check_ids


CANON_REMEDIATION: dict[str, str] = {
    "C1": "Run record_event.py --type phase_completed --source <phase>",
    "C2": "Run update_build_dashboard.py --phase <phase>",
    "C3": "Regenerate session_handoff.md via generate_session_handoff.py --reason '<phase>: ...'",
    "C4": "Add an ADR to .shipwright/agent_docs/decision_log.md via write_decision_log.py",
    "C5": "Prepend an Unreleased bullet via append_changelog_entry.py",
}


def run_canon_checks(phase: str, project_root: Path) -> list[dict[str, Any]]:
    """Run the C1-C5 Canon checks for ``phase`` and return finding dicts.

    Thin wrapper around ``tools/verifiers/common.py`` helpers so PR 1
    covers the standalone-Canon gap (plan § 1). Phase-specific verifier
    modules stay authoritative for the orchestrated path — this wrapper
    only runs the generic C1-C5 so it works uniformly for every plugin
    (including security + compliance which have no phase module).
    """
    skip_ids = skipped_check_ids()
    findings: list[dict[str, Any]] = []

    def _emit(check_id: str, result: CheckResult) -> None:
        if check_id in skip_ids:
            override = override_reason() or "skipped via SHIPWRIGHT_SKIP_QUALITY_CHECK"
            skip_result = CheckResult(
                name=result.name,
                ok=None,
                detail=override,
                severity=Severity.SKIPPED.value,
            )
            findings.append(_check_result_to_finding(
                skip_result, default_id=check_id,
                remediation=CANON_REMEDIATION.get(check_id, ""),
                provenance="override",
            ))
            return
        findings.append(_check_result_to_finding(
            result, default_id=check_id,
            remediation=CANON_REMEDIATION.get(check_id, ""),
        ))

    _emit("C1", check_c1_phase_event_recorded(project_root, phase))
    _emit("C2", check_c2_dashboard_reflects_phase(project_root, phase))
    _emit("C3", check_c3_session_handoff_fresh_after_phase(project_root, phase))

    if phase in C4_PHASES:
        _emit("C4", check_c4_decision_log_has_phase_adr(project_root, phase))
    else:
        findings.append({
            "id": "C4", "name": f"C4 decision_log has {phase} ADR",
            "status": STATUS_SKIP,
            "evidence": f"not applicable for phase={phase}",
        })

    if phase in C5_PHASES:
        category = C5_CATEGORY.get(phase, "Added")
        _emit("C5", check_c5_changelog_unreleased_has_phase_entry(
            project_root, phase, category,
        ))
    else:
        findings.append({
            "id": "C5", "name": "C5 CHANGELOG [Unreleased] has entry",
            "status": STATUS_SKIP,
            "evidence": f"not applicable for phase={phase}",
        })

    return findings


# ---------------------------------------------------------------------------
# Workflow dispatcher — per-phase wrappers live in tools/verifiers/*_compliance
# ---------------------------------------------------------------------------

# Lazy imports to avoid circular-import pain and keep startup cost low when
# a phase has no workflow checks (e.g. project). Each wrapper module exposes
# ``run(project_root, run_id) -> list[dict]``.
_WORKFLOW_PHASE_DISPATCH: dict[str, str] = {
    "build": "build_compliance",
    "iterate": "iterate_compliance",
    "test": "test_compliance",
    "plan": "plan_compliance",
    "changelog": "changelog_compliance",
    "deploy": "deploy_compliance",
    "security": "security_compliance",
    "compliance": "compliance_compliance",
    "design": "design_compliance",
    "adopt": "adopt_compliance",
}


def run_workflow_checks(phase: str, project_root: Path, run_id: str) -> list[dict[str, Any]]:
    """Dispatch to the per-phase ``*_compliance.py`` wrapper.

    Phases without workflow checks (``project``) return an empty list. Any
    internal failure inside a wrapper is converted into a single error
    finding so the Stop hook stays non-blocking (plan § 5.5).
    """
    module_name = _WORKFLOW_PHASE_DISPATCH.get(phase)
    if not module_name:
        return []
    skip_ids = skipped_check_ids()
    try:
        import importlib
        # `module_name` comes from the internal _WORKFLOW_PHASE_DISPATCH allowlist (no user input).
        # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
        module = importlib.import_module(f"tools.verifiers.{module_name}")
        findings = module.run(project_root, run_id)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[phase-quality] workflow wrapper {module_name} raised "
            f"{type(exc).__name__}: {exc}\n"
        )
        return [{
            "id": f"WF-{phase}",
            "name": f"workflow runner for {phase}",
            "status": STATUS_FAIL,
            "evidence": f"wrapper crashed: {type(exc).__name__}: {exc}",
            "provenance": "error",
        }]
    return [apply_skip_override(f, skip_ids) for f in findings]


def _dispatch_shared_category(
    phase: str,
    project_root: Path,
    module_name: str,
) -> list[dict[str, Any]]:
    """Shared wrapper for the Infra/Trace/Quality cross-phase modules.

    Mirrors ``run_workflow_checks``: lazy import, per-check SKIP-override,
    and try/except so a broken module surfaces as one error-finding
    rather than crashing the Stop hook (plan § 5.5).
    """
    skip_ids = skipped_check_ids()
    try:
        import importlib
        # `module_name` is a caller-supplied internal verifier name (Infra/Trace/Quality), not user input.
        # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
        module = importlib.import_module(f"tools.verifiers.{module_name}")
        findings = module.run(phase, project_root)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[phase-quality] {module_name} raised "
            f"{type(exc).__name__}: {exc}\n"
        )
        return [{
            "id": f"{module_name.upper()[:3]}-{phase}",
            "name": f"{module_name} runner for {phase}",
            "status": STATUS_FAIL,
            "evidence": f"wrapper crashed: {type(exc).__name__}: {exc}",
            "provenance": "error",
        }]
    return [apply_skip_override(f, skip_ids) for f in findings]


def run_infrastructure_checks(phase: str, project_root: Path) -> list[dict[str, Any]]:
    """Dispatch I1-I4 per the Plugin-Coverage table (plan § 5.1).

    Phases covered: build, iterate (I1-I4); test (I2); changelog (I3).
    Other phases return an empty list — infrastructure doesn't apply.
    """
    return _dispatch_shared_category(phase, project_root, "infrastructure_checks")


def run_traceability_checks(phase: str, project_root: Path) -> list[dict[str, Any]]:
    """Dispatch T1-T2 per the Plugin-Coverage table (plan § 5.1).

    Phases covered: project, iterate. Other phases return [].
    """
    return _dispatch_shared_category(phase, project_root, "traceability_checks")


def run_quality_checks(phase: str, project_root: Path) -> list[dict[str, Any]]:
    """Dispatch Q1-Q2 per the Plugin-Coverage table (plan § 5.1).

    Phases covered: project (Q1), plan (Q1), build (Q1+Q2),
    iterate (Q1). Other phases return [].
    """
    return _dispatch_shared_category(phase, project_root, "quality_checks")


def run_spec_checks(phase: str, project_root: Path, run_id: str) -> list[dict[str, Any]]:
    """Dispatch S1-S10 per the Plugin-Coverage table (plan § 5.1).

    Phases covered: project (S1, S5-S8), iterate (S2-S5, S9-S10). Other
    phases return []. Internal failures surface as a single error
    finding so the Stop hook stays non-blocking (plan § 5.5).
    """
    if phase not in {"project", "iterate"}:
        return []
    skip_ids = skipped_check_ids()
    try:
        import importlib
        module = importlib.import_module("tools.verifiers.spec_checks")
        findings = module.run(phase, project_root, run_id)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[phase-quality] spec_checks raised "
            f"{type(exc).__name__}: {exc}\n"
        )
        return [{
            "id": f"SPEC-{phase}",
            "name": f"spec runner for {phase}",
            "status": STATUS_FAIL,
            "evidence": f"wrapper crashed: {type(exc).__name__}: {exc}",
            "provenance": "error",
        }]
    return [apply_skip_override(f, skip_ids) for f in findings]


__all__ = [
    "CANON_REMEDIATION",
    "run_canon_checks",
    "run_infrastructure_checks",
    "run_quality_checks",
    "run_spec_checks",
    "run_traceability_checks",
    "run_workflow_checks",
]

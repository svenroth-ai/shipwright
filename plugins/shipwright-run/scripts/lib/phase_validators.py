"""Phase validation gates for the Shipwright pipeline.

Each validator checks whether a phase produced its required artifacts.
Returns (valid, issues) where issues have severity 'ask' or 'inform'.

Usage:
    from lib.phase_validators import validate_phase
    valid, issues = validate_phase("test", project_root)
    # issues: [{"severity": "ask", "message": "Smoke test skipped without reason"}]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Add shared scripts to path for imports
import sys
_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent.parent.parent / "shared" / "scripts"
sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.config import read_config, collect_all_build_sections  # noqa: E402


def _run_canon_checks(
    phase: str,
    project_root: Path,
    issues: list[dict[str, str]],
) -> None:
    """Shared canon verifier bridge used by every iterate-12 phase
    validator (project in 12.1; design + plan in 12.2).

    Dispatches to the matching ``tools.verifiers.<phase>_checks``
    module lazily so the import never fires in older test suites that
    stubbed ``phase_validators`` without these files on the path.
    Appends ask-level issues for every ERROR-severity result and
    inform-level issues for every WARNING. SKIPPED and green results
    are ignored.
    """
    try:
        from tools.verifiers.common import Severity
        if phase == "project":
            from tools.verifiers.project_checks import run_project_checks as _run
        elif phase == "design":
            from tools.verifiers.design_checks import run_design_checks as _run
        elif phase == "plan":
            from tools.verifiers.plan_checks import run_plan_checks as _run
        elif phase == "build":
            from tools.verifiers.build_checks import run_build_checks as _run
        elif phase == "test":
            from tools.verifiers.test_checks import run_test_checks as _run
        elif phase == "changelog":
            from tools.verifiers.changelog_checks import run_changelog_checks as _run
        elif phase == "deploy":
            from tools.verifiers.deploy_checks import run_deploy_checks as _run
        else:
            return
    except ImportError:
        return

    import os
    run_id = os.environ.get("SHIPWRIGHT_RUN_ID", "")
    for r in _run(project_root, run_id=run_id):
        if r.is_skipped or r.ok:
            continue
        severity = "ask" if r.severity == Severity.ERROR.value else "inform"
        issues.append({
            "severity": severity,
            "message": f"[canon] {r.name}: {r.detail}",
        })


def validate_phase(step: str, project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Validate a phase before marking it complete.

    Returns:
        (valid, issues) where valid=True means no ask-level issues.
        Issues list may still contain inform-level notes even when valid=True.
    """
    validator = _VALIDATORS.get(step)
    if validator is None:
        return True, []
    return validator(project_root)


def _validate_project(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Project phase: config exists, splits defined, spec files present,
    plus the iterate 12.1 Minimum Phase Completion Canon (C1/C2/C3/C4/C5
    + phase_history + ADR integrity) via the modular verifier.
    """
    issues: list[dict[str, str]] = []
    config = read_config("project", project_root)

    if not config:
        issues.append({
            "severity": "ask",
            "message": "No shipwright_project_config.json found. Was /shipwright-project completed?",
        })
        return False, issues

    splits = config.get("splits", [])
    if not splits:
        issues.append({
            "severity": "ask",
            "message": "No splits defined in project config. Did requirements decomposition complete?",
        })
        return False, issues

    missing_specs = []
    for sp in splits:
        name = sp.get("name", "")
        spec_path = project_root / ".shipwright" / "planning" / name / "spec.md"
        if not spec_path.exists():
            missing_specs.append(name)

    if missing_specs:
        issues.append({
            "severity": "ask",
            "message": f"Missing spec.md for splits: {', '.join(missing_specs)}. Continue without them?",
        })
        return False, issues

    # Iterate 12.1 — run the modular project canon verifier via the
    # shared _run_canon_checks bridge. ERROR-severity failures surface
    # as ask-level issues (block pipeline), WARNING results surface as
    # inform-level notes.
    _run_canon_checks("project", project_root, issues)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_design(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Design phase: mockup HTML files exist (ASK — design may be
    intentionally skipped). Iterate 12.2 augments with the modular
    ``design_checks`` verifier (manifest screen existence, FR coverage,
    canon C1/C2/C3/C5, ``phase_history``, ADR integrity). C4 is skipped
    by policy — design is a transformation, not a decision-taking phase.
    """
    issues: list[dict[str, str]] = []
    config = read_config("project", project_root)
    splits = config.get("splits", [])

    missing_mockups = []
    for sp in splits:
        name = sp.get("name", "")
        mockup_dir = project_root / ".shipwright" / "planning" / name / "mockups"
        if not mockup_dir.exists() or not list(mockup_dir.glob("*.html")):
            missing_mockups.append(name)

    if missing_mockups:
        issues.append({
            "severity": "ask",
            "message": (
                f"No mockups found for splits: {', '.join(missing_mockups)}. "
                "Was design skipped intentionally?"
            ),
        })
        return False, issues

    _run_canon_checks("design", project_root, issues)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_plan(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Plan phase: sections defined and section files exist. Iterate 12.2
    augments with the modular ``plan_checks`` verifier (config status,
    section manifest drift, FR orphans, section id validity, canon
    C1/C2/C3/C4, ``phase_history``, ADR integrity). C5 is skipped by
    policy — plan is an internal decomposition, not user-facing.
    """
    issues: list[dict[str, str]] = []
    build_config = read_config("build", project_root)

    sections = build_config.get("sections", [])
    if not sections:
        issues.append({
            "severity": "ask",
            "message": "No sections found in build config. Did /shipwright-plan complete?",
        })
        return False, issues

    current_split = build_config.get("current_split", "")
    missing_files = []
    for sec in sections:
        name = sec.get("name", "")
        section_path = project_root / ".shipwright" / "planning" / current_split / "sections" / f"{name}.md"
        if not section_path.exists():
            missing_files.append(name)

    if missing_files:
        issues.append({
            "severity": "ask",
            "message": (
                f"Missing section files for: {', '.join(missing_files)}. "
                "Continue without them?"
            ),
        })
        return False, issues

    _run_canon_checks("plan", project_root, issues)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_build(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Build phase: all current-split sections complete with tests.

    Uses ``collect_all_build_sections`` to check only the current
    split, not all splits. This avoids false negatives during the
    split-loop. Iterate 12.3 augments with the modular ``build_checks``
    verifier (per-section C1/C4, phase-level C2/C3/C5, phase_history
    with sections sub-array, B3 test-file existence, B6 commit
    reachability, ADR integrity).
    """
    issues: list[dict[str, str]] = []
    build_info = collect_all_build_sections(project_root)
    sections = build_info["current"]

    if not sections:
        issues.append({
            "severity": "ask",
            "message": "No sections found for current split. Was /shipwright-build run?",
        })
        return False, issues

    incomplete = [s.get("name", "?") for s in sections if s.get("status") != "complete"]
    if incomplete:
        issues.append({
            "severity": "ask",
            "message": (
                f"Sections not complete: {', '.join(incomplete)}. "
                "Continue with incomplete sections?"
            ),
        })
        return False, issues

    no_tests = [s.get("name", "?") for s in sections if s.get("tests_total", 0) == 0]
    if no_tests:
        issues.append({
            "severity": "ask",
            "message": (
                f"Sections with no tests: {', '.join(no_tests)}. "
                "Continue without test coverage?"
            ),
        })
        return False, issues

    _run_canon_checks("build", project_root, issues)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_test(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Test phase: results file exists, all layers have results or valid skip reasons.

    Standalone-mode results (mode == "standalone") are ignored by the pipeline
    validator — the test phase must run again within the pipeline context.
    """
    issues: list[dict[str, str]] = []
    results_path = project_root / "shipwright_test_results.json"

    if not results_path.exists():
        issues.append({
            "severity": "ask",
            "message": "No shipwright_test_results.json found. Were tests actually executed?",
        })
        return False, issues

    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        issues.append({
            "severity": "ask",
            "message": "shipwright_test_results.json is corrupt or unreadable. Re-run tests?",
        })
        return False, issues

    # Ignore standalone results — pipeline must run its own test phase
    if results.get("mode") == "standalone":
        issues.append({
            "severity": "ask",
            "message": (
                "Test results were produced in standalone mode (not part of this pipeline run). "
                "Re-run /shipwright-test within the pipeline for accurate validation."
            ),
        })
        return False, issues

    has_ask = False

    # Unit tests: must have results
    unit = results.get("unit", {})
    if not unit or unit.get("total", 0) == 0:
        issues.append({
            "severity": "ask",
            "message": "Unit test layer has no results. Were unit tests executed?",
        })
        has_ask = True

    # Integration tests: optional — only validate if present or profile requires them
    integration = results.get("integration", {})
    integration_skipped = integration.get("skipped", False)
    if integration and not integration_skipped and integration.get("total", 0) > 0:
        if integration.get("passed", 0) < integration.get("total", 0):
            issues.append({
                "severity": "ask",
                "message": (
                    f"Integration tests failing: {integration.get('passed', 0)}/{integration['total']} passed. "
                    "Fix before continuing?"
                ),
            })
            has_ask = True
    elif integration_skipped and not integration.get("skip_reason") and not integration.get("reason"):
        issues.append({
            "severity": "ask",
            "message": "Integration tests were skipped without a reason. Was this intentional?",
        })
        has_ask = True

    # pgTAP tests: optional — only validate if present
    pgtap = results.get("pgtap", {})
    pgtap_skipped = pgtap.get("skipped", False)
    if pgtap and not pgtap_skipped and pgtap.get("total", 0) > 0:
        if pgtap.get("passed", 0) < pgtap.get("total", 0):
            issues.append({
                "severity": "ask",
                "message": (
                    f"pgTAP tests failing: {pgtap.get('passed', 0)}/{pgtap['total']} passed. "
                    "Fix before continuing?"
                ),
            })
            has_ask = True

    # Smoke test: must have status or valid skip reason
    smoke = results.get("smoke", {})
    smoke_status = smoke.get("status", "")
    if not smoke_status:
        issues.append({
            "severity": "ask",
            "message": "Smoke test layer has no result. Continue without smoke test?",
        })
        has_ask = True
    elif smoke_status == "skip" and not smoke.get("reason"):
        issues.append({
            "severity": "ask",
            "message": "Smoke test was skipped without a reason. Was this intentional?",
        })
        has_ask = True

    # E2E: must have status or valid skip reason
    e2e = results.get("e2e", {})
    e2e_skipped = e2e.get("skipped", False)
    if not e2e and not e2e_skipped:
        issues.append({
            "severity": "ask",
            "message": "E2E test layer has no result. Continue without E2E tests?",
        })
        has_ask = True
    elif e2e_skipped and not e2e.get("reason"):
        issues.append({
            "severity": "ask",
            "message": "E2E tests were skipped without a reason. Was this intentional?",
        })
        has_ask = True

    # --- Outcome checks (after existence checks) ---

    # Unit: blocking — must pass
    if unit.get("total", 0) > 0 and unit.get("passed", 0) < unit.get("total", 0):
        issues.append({
            "severity": "ask",
            "message": (
                f"Unit tests failing: {unit.get('passed', 0)}/{unit['total']} passed. "
                "Fix before continuing?"
            ),
        })
        has_ask = True

    # Smoke: blocking — must pass
    if smoke_status == "fail":
        issues.append({
            "severity": "ask",
            "message": "Smoke test failed — app not responding correctly. Continue anyway?",
        })
        has_ask = True

    # E2E: non-blocking — warn only (per constitution, E2E can be flaky)
    e2e_passed = e2e.get("passed", 0)
    e2e_total = e2e.get("total", 0)
    if e2e_total > 0 and e2e_passed < e2e_total:
        issues.append({
            "severity": "inform",
            "message": (
                f"E2E tests: {e2e_passed}/{e2e_total} passed. "
                f"{e2e_total - e2e_passed} failures logged as warnings."
            ),
        })

    # Consistency: non-blocking — inform only (cross-page cosmetic issues)
    consistency = results.get("consistency", {})
    if consistency and not consistency.get("skipped", False):
        cons_total = consistency.get("total", 0)
        cons_passed = consistency.get("passed", 0)
        if cons_total > 0 and cons_passed < cons_total:
            issues.append({
                "severity": "inform",
                "message": (
                    f"UI consistency: {cons_passed}/{cons_total} categories consistent. "
                    f"{cons_total - cons_passed} inconsistencies logged."
                ),
            })

    _run_canon_checks("test", project_root, issues)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_changelog(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Changelog phase: CHANGELOG.md exists. Iterate 12.4 augments with
    the modular ``changelog_checks`` verifier (canon C1/C2/C3 +
    Sonder-Checks ``check_git_tag_exists`` and
    ``check_changelog_version_matches_tag`` + ``phase_history`` + ADR
    integrity). C4/C5 are skipped by policy.
    """
    issues: list[dict[str, str]] = []

    if not (project_root / "CHANGELOG.md").exists():
        issues.append({
            "severity": "ask",
            "message": "No CHANGELOG.md found. Was /shipwright-changelog completed?",
        })
        return False, issues

    _run_canon_checks("changelog", project_root, issues)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_deploy(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Deploy phase: iterate 12.4 wires the modular ``deploy_checks``
    verifier (test-gate pre-condition + canon C1/C2/C3 + phase_history
    + ADR integrity). C4/C5 are skipped by policy (deploy is execution
    + operational history, not a decision or product change).
    """
    issues: list[dict[str, str]] = []
    _run_canon_checks("deploy", project_root, issues)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_compliance(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Compliance phase: check artifacts exist. INFORM only — non-blocking."""
    issues: list[dict[str, str]] = []
    compliance_dir = project_root / "compliance"

    required = ["dashboard.md", "traceability-matrix.md", "test-evidence.md", "change-history.md", "sbom.md"]
    present = []
    missing = []

    for name in required:
        if (compliance_dir / name).exists():
            present.append(name)
        else:
            missing.append(name)

    if missing:
        issues.append({
            "severity": "inform",
            "message": (
                f"Compliance artifacts: {len(present)}/{len(required)} present. "
                f"Missing: {', '.join(missing)}."
            ),
        })
    else:
        issues.append({
            "severity": "inform",
            "message": f"All {len(required)} compliance artifacts present.",
        })

    # Inform-level issues never make valid=False
    return True, issues


_VALIDATORS: dict[str, Any] = {
    "project": _validate_project,
    "design": _validate_design,
    "plan": _validate_plan,
    "build": _validate_build,
    "test": _validate_test,
    "changelog": _validate_changelog,
    "deploy": _validate_deploy,
    "compliance": _validate_compliance,
}

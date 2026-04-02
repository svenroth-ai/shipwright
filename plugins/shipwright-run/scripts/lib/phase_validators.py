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

from lib.config import read_config, collect_all_build_sections


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
    """Project phase: config exists, splits defined, spec files present."""
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
        spec_path = project_root / "planning" / name / "spec.md"
        if not spec_path.exists():
            missing_specs.append(name)

    if missing_specs:
        issues.append({
            "severity": "ask",
            "message": f"Missing spec.md for splits: {', '.join(missing_specs)}. Continue without them?",
        })
        return False, issues

    return True, []


def _validate_design(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Design phase: mockup HTML files exist (ASK — design may be intentionally skipped)."""
    issues: list[dict[str, str]] = []
    config = read_config("project", project_root)
    splits = config.get("splits", [])

    missing_mockups = []
    for sp in splits:
        name = sp.get("name", "")
        mockup_dir = project_root / "planning" / name / "mockups"
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

    return True, []


def _validate_plan(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Plan phase: sections defined and section files exist."""
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
        section_path = project_root / "planning" / current_split / "sections" / f"{name}.md"
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

    return True, []


def _validate_build(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Build phase: all current-split sections complete with tests.

    Uses get_build_progress() logic to check only the current split,
    not all splits. This avoids false negatives during split-loop.
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

    return True, []


def _validate_test(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Test phase: results file exists, all layers have results or valid skip reasons."""
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

    has_ask = False

    # Unit tests: must have results
    unit = results.get("unit", {})
    if not unit or unit.get("total", 0) == 0:
        issues.append({
            "severity": "ask",
            "message": "Unit test layer has no results. Were unit tests executed?",
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

    return not has_ask, issues


def _validate_changelog(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Changelog phase: CHANGELOG.md exists."""
    issues: list[dict[str, str]] = []

    if not (project_root / "CHANGELOG.md").exists():
        issues.append({
            "severity": "ask",
            "message": "No CHANGELOG.md found. Was /shipwright-changelog completed?",
        })
        return False, issues

    return True, []


def _validate_deploy(project_root: Path) -> tuple[bool, list[dict[str, str]]]:
    """Deploy phase: always passes (deploy handles its own success/failure)."""
    return True, []


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

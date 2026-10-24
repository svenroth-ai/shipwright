"""Phase validation gates for the Shipwright pipeline.

Each validator checks whether a phase produced its required artifacts.
Returns (valid, issues) where issues have severity 'ask' or 'inform'.

Usage:
    from lib.phase_validators import validate_phase
    valid, issues = validate_phase("test", project_root)
    # issues: [{"severity": "ask", "message": "Smoke test skipped without reason"}]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Add shared scripts to path for imports
import sys
_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent.parent.parent / "shared" / "scripts"
sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.config import read_config, collect_all_build_sections  # noqa: E402

# Sibling modules are imported by bare name; this file is also loaded by path.
_LIB_DIR = str(Path(__file__).resolve().parent)
if _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)

from phase_validators_canon import _run_canon_checks  # noqa: E402,F401
from phase_validators_late import (  # noqa: E402
    _validate_changelog,
    _validate_compliance,
    _validate_deploy,
    _validate_test,
)


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

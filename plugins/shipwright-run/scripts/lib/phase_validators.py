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

from lib.config import read_config  # noqa: E402

# Sibling modules are imported by bare name; this file is also loaded by path.
_LIB_DIR = str(Path(__file__).resolve().parent)
if _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)

from phase_validators_canon import _run_canon_checks  # noqa: E402
from phase_validators_late import (  # noqa: E402
    _validate_changelog,
    _validate_compliance,
    _validate_deploy,
    _validate_test,
)
from phase_validators_split import (  # noqa: E402
    _validate_design,
    _validate_plan,
    sections_for_split,
)


def validate_phase(
    step: str, project_root: Path, *, split_id: str | None = None, run_id: str | None = None,
) -> tuple[bool, list[dict[str, str]]]:
    """Validate a phase before marking it complete.

    ``split_id`` is the phase task's own split (plan reads its sections from it);
    ``run_id`` is handed to the canon bridge, which falls back to ``SHIPWRIGHT_RUN_ID``
    only when it is None and reports a degraded note when no run id is known.

    Returns:
        (valid, issues) where valid=True means no ask-level issues.
        Issues list may still contain inform-level notes even when valid=True.
    """
    validator = _VALIDATORS.get(step)
    if validator is None:
        return True, []
    return validator(project_root, split_id=split_id, run_id=run_id)


def _validate_project(
    project_root: Path, *, split_id: str | None = None, run_id: str | None = None,
) -> tuple[bool, list[dict[str, str]]]:
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
    _run_canon_checks("project", project_root, issues, run_id=run_id)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_build(
    project_root: Path, *, split_id: str | None = None, run_id: str | None = None,
) -> tuple[bool, list[dict[str, str]]]:
    """Build phase: all sections of the task's split complete with tests.

    Only that split is checked, not all splits. Its sections are the build config's
    current ones, or — for a non-final split the build skill already archived
    (``archive_split`` moves them to ``split_<prefix>_sections`` before the result is
    applied) — that archived bucket (``sections_for_split``). No ``split_id``: the current
    split, as before. Iterate 12.3 augments with the modular ``build_checks`` verifier
    (per-section C1/C4, phase-level C2/C3/C5, phase_history with sections sub-array, B3
    test-file existence, B6 commit reachability, ADR integrity), given the same split.

    An archived split's ask-level findings carry ``kind: archived_split`` (not retryable,
    ``phase_gate.is_retryable``): a re-dispatched build works on ``current_split``, so a
    retry cannot fix the split that was already filed away — a person decides.
    """
    build_config = read_config("build", project_root)
    current = build_config.get("current_split") or ""
    archived = bool(split_id and current and split_id != current)
    issues = _build_issues(project_root, sections_for_split(build_config, split_id),
                           split_id=split_id, archived=archived, run_id=run_id)
    if archived:
        for issue in issues:
            if issue["severity"] == "ask":  # the flag survives a finding with its own kind
                issue.setdefault("kind", "archived_split")
                issue["archived_split"] = True
    return not any(i["severity"] == "ask" for i in issues), issues


def _build_issues(
    project_root: Path, sections: list, *, split_id: str | None, archived: bool,
    run_id: str | None,
) -> list[dict[str, str]]:
    """The build gate's findings for ``sections`` (the gated split's own). The canon checks
    get the split only when it is ``archived``: for the current split they read the same
    sections without it, so an older installed verifier is not refused for nothing."""
    issues: list[dict[str, str]] = []
    if not sections:
        where = f"split '{split_id}'" if archived else "current split"
        issues.append({
            "severity": "ask",
            "message": f"No sections found for {where}. Was /shipwright-build run?",
        })
        return issues

    incomplete = [s.get("name", "?") for s in sections if s.get("status") != "complete"]
    if incomplete:
        issues.append({
            "severity": "ask",
            "message": (
                f"Sections not complete: {', '.join(incomplete)}. "
                "Continue with incomplete sections?"
            ),
        })
        return issues

    no_tests = [s.get("name", "?") for s in sections if s.get("tests_total", 0) == 0]
    if no_tests:
        issues.append({
            "severity": "ask",
            "message": (
                f"Sections with no tests: {', '.join(no_tests)}. "
                "Continue without test coverage?"
            ),
        })
        return issues

    _run_canon_checks("build", project_root, issues, run_id=run_id,
                      split_id=split_id if archived else None)
    return issues


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

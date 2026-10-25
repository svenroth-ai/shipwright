"""Design and plan phase validators: the two whose answer depends on the splits.

Import this only through ``phase_validators`` (it puts ``shared/scripts`` and this lib
dir on ``sys.path``). Split membership comes from ``_resolve_splits_with_fallback`` —
the same authority ``freeze_splits`` uses (design config first, then project config) —
so the gate and the split loop can never disagree about which splits exist.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from lib.config import read_config
from phase_task_planning import _resolve_splits_with_fallback
from phase_validators_canon import _run_canon_checks

# Mirrors ``tools.verifiers.design_checks._NO_UI_SCOPES`` (pinned equal by a test): a
# project with no UI surface has nothing for the design phase to produce.
_NO_UI_SCOPES = frozenset({"library"})


def _read_json(path: Path) -> dict:
    """A config as a dict; absent, unreadable or non-object reads as empty (BOM-tolerant)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def sections_for_split(build_config: dict, split_id: Optional[str]) -> list:
    """The build sections of ``split_id``: the current list, unless ``current_split`` has
    moved on to another split (both known, different) — then the bucket ``archive_split``
    filed it under (``split_<prefix>_sections``) when ``archive_split`` recorded this exact
    name in ``completed_splits`` (a prefix alone can be shared or left over), or ``[]``.
    The build skill archives a non-final split BEFORE the driven run applies its result.
    Mirrors ``tools.verifiers.build_split.sections_for_split`` (pinned equal by a test)."""
    if not isinstance(build_config, dict):
        return []
    sections = build_config.get("sections")
    current = build_config.get("current_split") or ""
    if split_id and current and split_id != current:
        done = build_config.get("completed_splits")
        sections = (build_config.get(f"split_{split_id.split('-', 1)[0]}_sections")
                    if isinstance(done, list) and split_id in done else None)
    return sections if isinstance(sections, list) else []


def _has_html(directory: Path) -> bool:
    return directory.is_dir() and any(directory.glob("*.html"))


def _design_not_applicable(project_root: Path) -> Optional[str]:
    """Why this run has no screens to check, or None when it should have them.

    Only the run's scope decides (``scope=library`` in ``shipwright_run_config.json``,
    the same rule as the design verifier's ``_is_no_ui_scope``). A ``skipped`` design
    task in ``phase_tasks[]`` is deliberately NOT an exemption: a skipped task is
    terminal and never gated, and the status is reachable through
    ``recover-phase-task --force-status skipped``, so honouring it here would let a
    later completion launder a skip into a clean pass.
    """
    run_config = _read_json(project_root / "shipwright_run_config.json")
    if run_config.get("scope") in _NO_UI_SCOPES:
        return f"scope={run_config['scope']} has no UI surface"
    return None


def _validate_design(
    project_root: Path, *, split_id: Optional[str] = None, run_id: Optional[str] = None,
) -> tuple[bool, list[dict[str, str]]]:
    """Design phase: screens exist, then the modular ``design_checks`` canon verifier.

    Screens are project-global (``.shipwright/designs/screens/*.html``, where the design
    skill writes them). Only when that directory has none is the older per-split layout
    (``.shipwright/planning/<split>/mockups/*.html``) consulted, and then EVERY split —
    or the task's own split when one is given — must have mockups. No screens and no
    splits is a failure, not a vacuous pass. A run with no UI skips only this presence
    check (inform note); the canon verifier still runs, as ``design_checks`` does.
    """
    issues: list[dict[str, str]] = []
    not_applicable = _design_not_applicable(project_root)
    if not_applicable:
        issues.append({
            "severity": "inform",
            "message": f"Design screen check not applicable: {not_applicable}.",
        })
    elif not _has_html(project_root / ".shipwright" / "designs" / "screens"):
        splits, _source, _warning = _resolve_splits_with_fallback(project_root)
        wanted = [split_id] if split_id else splits
        missing = [
            s for s in wanted
            if s not in splits
            or not _has_html(project_root / ".shipwright" / "planning" / s / "mockups")
        ]
        if not wanted or missing:
            where = f" or per split for: {', '.join(missing)}" if missing else ""
            issues.append({
                "severity": "ask",
                "message": (
                    f"No mockups found in .shipwright/designs/screens/{where}. "
                    "Was design skipped intentionally?"
                ),
            })
            return False, issues

    _run_canon_checks("design", project_root, issues, run_id=run_id)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_plan(
    project_root: Path, *, split_id: Optional[str] = None, run_id: Optional[str] = None,
) -> tuple[bool, list[dict[str, str]]]:
    """Plan phase: sections defined and section files exist for the TASK's split.

    ``split_id`` is the plan task's own split and must be one of the run's resolved
    splits when there are any. Only then does the check also keep it from naming a path
    outside ``.shipwright/planning/``: with no resolvable splits the id is used as given
    (an existence check only, nothing is read). Without one (a split-less run, or a caller
    that does not know it) the build config's ``current_split`` is used, as before. When
    both are known and differ, the task split's archived sections are used; if there are
    none, that is reported instead of checking the wrong directory. With neither split
    known the split-less layout ``.shipwright/planning/sections/`` is checked (unchanged).
    Then the ``plan_checks`` canon.
    """
    issues: list[dict[str, str]] = []
    build_config = read_config("build", project_root)

    if split_id:
        splits, _source, _warning = _resolve_splits_with_fallback(project_root)
        if splits and split_id not in splits:
            issues.append({
                "severity": "ask",
                "message": (
                    f"Plan task split '{split_id}' is not one of this run's splits "
                    f"({', '.join(splits)}). Is the task's split correct?"
                ),
            })
            return False, issues

    recorded_split = build_config.get("current_split", "") or ""
    sections = build_config.get("sections", [])
    if split_id and recorded_split and recorded_split != split_id:
        # A finished split's sections are archived under split_<prefix>_sections (the
        # key collect_all_build_sections reads), so a re-check after current_split moved
        # on still finds them.
        archived = sections_for_split(build_config, split_id)
        if not archived:
            issues.append({
                "severity": "ask",
                "message": (
                    f"Build config lists sections for split '{recorded_split}', but this plan "
                    f"task is for split '{split_id}'. Re-run /shipwright-plan for '{split_id}'?"
                ),
            })
            return False, issues
        sections = archived

    if not sections:
        issues.append({
            "severity": "ask",
            "message": "No sections found in build config. Did /shipwright-plan complete?",
        })
        return False, issues

    split = split_id or recorded_split
    missing_files = [
        sec.get("name", "") for sec in sections
        if not (project_root / ".shipwright" / "planning" / split / "sections"
                / f"{sec.get('name', '')}.md").exists()
    ]
    if missing_files:
        issues.append({
            "severity": "ask",
            "message": (
                f"Missing section files for: {', '.join(missing_files)}. "
                "Continue without them?"
            ),
        })
        return False, issues

    _run_canon_checks("plan", project_root, issues, run_id=run_id)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues

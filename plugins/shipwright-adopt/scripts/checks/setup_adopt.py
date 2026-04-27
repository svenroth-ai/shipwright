#!/usr/bin/env python3
"""Pre-flight check for /shipwright-adopt.

Hard-stops if:
  - Not a git repo
  - shipwright_run_config.json already exists (already adopted)

Soft-warns if:
  - No commits yet
  - Dirty working tree (user must confirm via skill flow)

Reports nested projects via stdout JSON for the skill to consume.

Usage:
    uv run setup_adopt.py --project-root /path
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _is_git_repo(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _has_commits(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _working_tree_dirty(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return bool(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


_EXISTING_ARTIFACT_CANDIDATES: tuple[str, ...] = (
    "CLAUDE.md",
    ".shipwright/agent_docs/architecture.md",
    ".shipwright/agent_docs/conventions.md",
    ".shipwright/agent_docs/decision_log.md",
    ".shipwright/agent_docs/build_dashboard.md",
    # Tier-5 visual docs (sub-iterate E + F): adopt regenerates these from
    # source on each run, but the operator may have hand-edited them. Surface
    # them here so the SKILL.md prompt acknowledges they'll be touched, and
    # so `visual_docs_generator` can back them up.
    ".shipwright/agent_docs/design_tokens.md",
    ".shipwright/agent_docs/guideline.md",
    "shipwright_events.jsonl",
    "shipwright_sync_config.json",
    "shipwright_project_config.json",
    "shipwright_plan_config.json",
    "shipwright_build_config.json",
    "shipwright_compliance_config.json",
)


def _detect_existing_artifacts(project_root: Path) -> list[str]:
    """Return the relative paths of artifacts that adopt would touch.

    Used by the SKILL.md flow to confirm "Found N existing artifacts.
    Adopt will preserve+overwrite them. Continue?" before proceeding.
    Pre-existing files don't block adopt — preservation is automatic
    (see `lib/preserve_existing.py`) — but the user should know what's
    about to happen. spec.md files under .shipwright/planning/ are also
    surfaced.
    """
    found: list[str] = []
    for rel in _EXISTING_ARTIFACT_CANDIDATES:
        if (project_root / rel).is_file():
            found.append(rel)
    planning = project_root / ".shipwright" / "planning"
    if planning.is_dir():
        for spec in sorted(planning.rglob("spec.md")):
            try:
                rel = spec.relative_to(project_root).as_posix()
            except ValueError:
                continue
            found.append(rel)
    return found


def run_preflight(project_root: Path, excludes: list[str]) -> dict:
    """Return a preflight report. Non-zero exit on hard-stop."""
    report: dict = {
        "project_root": str(project_root),
        "ok": True,
        "hard_stops": [],
        "warnings": [],
        "nested_projects": [],
        "existing_artifacts": [],
    }

    if not _is_git_repo(project_root):
        report["ok"] = False
        report["hard_stops"].append(
            "Not a git repo. Run `git init` first, or use /shipwright-project for a new project."
        )
        return report

    if (project_root / "shipwright_run_config.json").exists():
        report["ok"] = False
        report["hard_stops"].append(
            "shipwright_run_config.json already exists — this project is already adopted. "
            "Use /shipwright-iterate for changes or /shipwright-compliance to refresh artifacts."
        )
        return report

    if not _has_commits(project_root):
        report["warnings"].append(
            "No commits yet. Change history will be empty. Consider committing once before adopting."
        )

    if _working_tree_dirty(project_root):
        report["warnings"].append(
            "Working tree is dirty. Adopt will create a single adoption commit; "
            "staged/unstaged changes would be mixed in. Consider `git stash` first."
        )

    # Existing artifacts — informational; adopt preserves them, but the
    # SKILL.md flow asks the user before proceeding when this list is non-empty.
    report["existing_artifacts"] = _detect_existing_artifacts(project_root)

    # Nested projects detection
    try:
        lib_path = Path(__file__).resolve().parent.parent / "lib"
        sys.path.insert(0, str(lib_path))
        from nested_project_detector import detect_nested_projects  # type: ignore
        report["nested_projects"] = [
            n for n in detect_nested_projects(project_root)
            if n["path"] not in excludes
        ]
    except Exception as e:  # pragma: no cover — defensive
        report["warnings"].append(f"Nested-project scan failed: {e!r}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight check for /shipwright-adopt")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--exclude-path", action="append", default=[])
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(f"ERROR: not a directory: {project_root}", file=sys.stderr)
        return 1
    report = run_preflight(project_root, args.exclude_path)
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

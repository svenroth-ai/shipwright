"""Write the 6 shipwright_*_config.json files for an adopted project.

Order matters: `shipwright_run_config.json` is written LAST so the
audit-on-Stop hook doesn't see a half-formed Shipwright project.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_project_config(
    project_root: Path,
    *,
    scope: str,
    profile: str,
    split_name: str,
    fr_count: int,
    qr_count: int,
) -> Path:
    config = {
        "status": "complete",
        "scope": scope,
        "profile": profile,
        "planning_dir": ".shipwright/planning",
        "splits": [{"name": split_name, "status": "adopted"}],
        "requirements": {
            "source": "inferred-from-codebase",
            "fr_count": fr_count,
            "qr_count": qr_count,
        },
        "artifacts": {
            "claude_md": True,
            "agent_docs": True,
            "manifest": False,
        },
        "adopted": True,
        "updated_at": _utc_now_iso(),
    }
    path = project_root / "shipwright_project_config.json"
    _write_json(path, config)
    return path


def write_plan_config(project_root: Path, *, split_name: str) -> Path:
    config = {
        "status": "adopted",
        "sections": [],
        "manifest": None,
        "note": (
            f"This project was adopted into Shipwright. Split '{split_name}' "
            "has no planned sections — existing code is treated as retroactively complete. "
            "Use /shipwright-iterate for all future changes."
        ),
        "external_review_feedback_iterations": 0,
        "updated_at": _utc_now_iso(),
    }
    path = project_root / "shipwright_plan_config.json"
    _write_json(path, config)
    return path


def write_build_config(
    project_root: Path,
    *,
    profile: str,
    dev_url: str | None,
    test_cmd: str | None,
    commit_sha: str | None,
) -> Path:
    config = {
        "status": "adopted",
        "dev_url": dev_url,
        "profile": profile,
        "test_cmd": test_cmd,
        "sections": [{
            "name": "adopted-baseline",
            "status": "adopted",
            "commit": commit_sha or "HEAD",
            "tests_total": 0,
            "tests_passed": 0,
        }],
        "current_split": None,
        "updated_at": _utc_now_iso(),
    }
    path = project_root / "shipwright_build_config.json"
    _write_json(path, config)
    return path


def write_compliance_config(project_root: Path) -> Path:
    config = {
        "enforcement": {"rtm_coverage_min": 0.7},
        "status": "initial",
        "last_full_generation": _utc_now_iso(),
        "seeded_by_adopt": True,
    }
    path = project_root / "shipwright_compliance_config.json"
    _write_json(path, config)
    return path


def write_sync_config(project_root: Path) -> Path:
    config = {
        "mappings": [],
        "file_to_fr_map": {},
        "note": "Empty by default. Populated incrementally by /shipwright-iterate as file changes get mapped to FRs.",
        "updated_at": _utc_now_iso(),
    }
    path = project_root / "shipwright_sync_config.json"
    _write_json(path, config)
    return path


def write_run_config(
    project_root: Path,
    *,
    scope: str,
    profile: str,
    plugin_version: str,
    commit_sha: str | None,
    features_inferred: int,
    nested_excluded: list[str],
    completed_steps: list[str],
) -> Path:
    now = _utc_now_iso()
    phase_history: dict[str, list[dict[str, Any]]] = {}
    for step in completed_steps:
        outcome = "adopted-skipped" if step == "test" else "adopted"
        phase_history[step] = [{
            "outcome": outcome,
            "run_id": f"adopt-{now[:19].replace(':', '')}",
            "at": now,
        }]
    config = {
        "pipeline": [
            "project", "design", "plan", "build",
            "test", "changelog", "deploy",
        ],
        "status": "complete",
        "current_step": None,
        "completed_steps": completed_steps,
        "profile": profile,
        "scope": scope,
        "autonomy": "supervised",
        "standalone": False,
        "adoption": {
            "adopted_at": now,
            "commit_at_adoption": commit_sha or "HEAD",
            "features_inferred": features_inferred,
            "nested_excluded": nested_excluded,
            "plugin_version": plugin_version,
        },
        "phase_history": phase_history,
        # iterate_history lives in .shipwright/agent_docs/iterates/*.json (file-per-iterate
        # refactor). The empty array below is kept for backward-compat with
        # any external reader that still does config.get("iterate_history", []);
        # the migration flag below tells new tooling the file-per-iterate store
        # is the canonical source so no first-touch migration ever runs on this
        # freshly-adopted project.
        "iterate_history": [],
        "_iterate_migration_state": "complete",
        "_iterate_migration_ts": now,
        "_iterate_migration_quarantined_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    path = project_root / "shipwright_run_config.json"
    _write_json(path, config)

    # Initialize the file-per-iterate directories with .gitkeep so a fresh
    # clone carries the structure even if no iterate has finalized yet. The
    # reader ignores .gitkeep by name and by non-.json extension.
    _init_iterate_store_dirs(project_root)
    _init_changelog_drop_dirs(project_root)

    return path


def _init_iterate_store_dirs(project_root: Path) -> None:
    """Create .shipwright/agent_docs/iterates/ with quarantine + meta subdirs."""
    base = project_root / ".shipwright" / "agent_docs" / "iterates"
    for sub in (base, base / "_quarantine", base / "_meta"):
        sub.mkdir(parents=True, exist_ok=True)
        gitkeep = sub / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")


def _init_changelog_drop_dirs(project_root: Path) -> None:
    """Create CHANGELOG-unreleased.d/<category>/ with .gitkeep per category.

    Must stay in sync with ALLOWED_CATEGORIES in write_changelog_drop.py.
    """
    base = project_root / "CHANGELOG-unreleased.d"
    for category in ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"):
        cat_dir = base / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = cat_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")


def write_all(
    project_root: Path,
    *,
    scope: str,
    profile: str,
    split_name: str,
    plugin_version: str,
    dev_url: str | None,
    test_cmd: str | None,
    commit_sha: str | None,
    features_inferred: int,
    nested_excluded: list[str],
    fr_count: int,
    qr_count: int,
    write_sync: bool = True,
    completed_steps: list[str] | None = None,
) -> list[Path]:
    """Write all six configs in the safe order. Returns paths in write order.

    Ordering: project → plan → build → compliance → sync → run (last).
    """
    if completed_steps is None:
        completed_steps = ["project", "plan", "build", "test"]
    paths: list[Path] = []
    paths.append(write_project_config(
        project_root,
        scope=scope, profile=profile, split_name=split_name,
        fr_count=fr_count, qr_count=qr_count,
    ))
    paths.append(write_plan_config(project_root, split_name=split_name))
    paths.append(write_build_config(
        project_root, profile=profile,
        dev_url=dev_url, test_cmd=test_cmd, commit_sha=commit_sha,
    ))
    paths.append(write_compliance_config(project_root))
    if write_sync:
        paths.append(write_sync_config(project_root))
    # RUN CONFIG LAST — trips Shipwright-aware hooks
    paths.append(write_run_config(
        project_root,
        scope=scope, profile=profile, plugin_version=plugin_version,
        commit_sha=commit_sha, features_inferred=features_inferred,
        nested_excluded=nested_excluded,
        completed_steps=completed_steps,
    ))
    return paths

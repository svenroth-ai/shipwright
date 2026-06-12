"""Config read/write for all shipwright_*_config.json files and the event log.

Each skill writes its own config file in the target project root:
  - shipwright_run_config.json
  - shipwright_project_config.json
  - shipwright_plan_config.json
  - shipwright_build_config.json
  - shipwright_compliance_config.json

Config files are used for orchestration and resume. The event log
(shipwright_events.jsonl) is the single source of truth for reporting.
"""

import json
import warnings
from pathlib import Path
from typing import Any

from .events_amend import apply_amendments  # noqa: F401 — re-exported SSOT
from .events_log import resolve_events_path

CONFIG_FILES = {
    "run": "shipwright_run_config.json",
    "project": "shipwright_project_config.json",
    "plan": "shipwright_plan_config.json",
    "build": "shipwright_build_config.json",
    "security": "shipwright_security_config.json",
    "compliance": "shipwright_compliance_config.json",
    "events": "shipwright_events.jsonl",
}

EVENT_FILE = "shipwright_events.jsonl"


def get_config_path(skill: str, project_root: str | Path) -> Path:
    """Get the config file path for a given skill."""
    if skill not in CONFIG_FILES:
        raise ValueError(f"Unknown skill: {skill}. Must be one of: {list(CONFIG_FILES.keys())}")
    return Path(project_root) / CONFIG_FILES[skill]


def read_config(skill: str, project_root: str | Path) -> dict[str, Any]:
    """Read a skill's config file. Returns empty dict if file doesn't exist."""
    path = get_config_path(skill, project_root)
    if not path.exists():
        return {}
    # ``utf-8-sig`` strips a leading UTF-8 BOM (a hand-edited config saved by
    # Windows Notepad as "UTF-8 with BOM" round-trips ``﻿`` that plain
    # ``utf-8`` decodes-but-keeps → ``json.loads`` JSONDecodeErrors on char 0).
    # Consistent with the four sibling config readers BOM-hardened in WP8/F24
    # (artifact_sync, suggest_iterate, classify_complexity, classify_intent).
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_config(skill: str, project_root: str | Path, data: dict[str, Any]) -> Path:
    """Write a skill's config file. Creates or overwrites."""
    path = get_config_path(skill, project_root)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def update_config(skill: str, project_root: str | Path, updates: dict[str, Any]) -> dict[str, Any]:
    """Read, merge updates, and write back. Returns the merged config."""
    config = read_config(skill, project_root)
    config.update(updates)
    write_config(skill, project_root, config)
    return config


def read_all_configs(project_root: str | Path) -> dict[str, dict[str, Any]]:
    """Read all JSON config files. Returns dict keyed by skill name.

    Skips non-JSON entries (like the JSONL event log).
    """
    return {
        skill: read_config(skill, project_root)
        for skill in CONFIG_FILES
        if not CONFIG_FILES[skill].endswith(".jsonl")
    }


def collect_all_build_sections(project_root: str | Path) -> dict[str, Any]:
    """Read all build sections across archived and current splits.

    Returns a dict with:
        archived: list of section dicts from completed splits
        current: list of section dicts from the current split
        all: archived + current combined
        current_split: name of the current split (or "")
        completed_splits: list of completed split names
        total_splits: total number of splits from project config
    """
    project_root = Path(project_root)
    build_config = read_config("build", project_root)
    project_config = read_config("project", project_root)

    splits = project_config.get("splits", [])
    total_splits = len(splits)

    # Build prefix -> split name lookup
    split_by_prefix: dict[str, str] = {}
    for sp in splits:
        prefix = sp.get("name", "").split("-", 1)[0]
        if prefix:
            split_by_prefix[prefix] = sp["name"]

    # Archived splits — tag each section with its split name
    archived: list[dict[str, Any]] = []
    for key, value in build_config.items():
        if key.startswith("split_") and key.endswith("_sections") and isinstance(value, list):
            prefix = key.split("_")[1]  # "split_01_sections" → "01"
            split_name = split_by_prefix.get(prefix, prefix)
            for sec in value:
                if "split" not in sec:
                    sec["split"] = split_name
            archived.extend(value)

    # Current split — tag sections with current split name
    current: list[dict[str, Any]] = build_config.get("sections", [])
    current_split = build_config.get("current_split", "")
    for sec in current:
        if "split" not in sec:
            sec["split"] = current_split
    completed_splits = build_config.get("completed_splits", [])

    return {
        "archived": archived,
        "current": current,
        "all": archived + current,
        "current_split": current_split,
        "completed_splits": completed_splits,
        "total_splits": total_splits,
    }


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------

def read_events(project_root: str | Path) -> list[dict[str, Any]]:
    """Read all events from the JSONL log. Tolerant — skips corrupt lines.

    Worktree-aware: resolves the canonical (main-repo) event log via
    ``resolve_events_path`` so the build dashboard renderer, run from inside
    a ``/shipwright-iterate`` worktree at F5b, reads the full event history
    rather than an absent/empty worktree-local copy.
    """
    path = resolve_events_path(project_root)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for i, line in enumerate(path.open("r", encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            warnings.warn(f"Corrupt event at line {i + 1} in {EVENT_FILE}, skipping")
    return events

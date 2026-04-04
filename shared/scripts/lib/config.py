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
    return json.loads(path.read_text(encoding="utf-8"))


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
    """Read all events from the JSONL log. Tolerant — skips corrupt lines."""
    path = Path(project_root) / EVENT_FILE
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


def apply_amendments(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply event_amended entries to their target events."""
    amendments: dict[str, dict] = {}
    for e in events:
        if e.get("type") == "event_amended":
            amendments[e["amends"]] = e.get("fields", {})

    result: list[dict[str, Any]] = []
    for e in events:
        if e.get("type") == "event_amended":
            continue
        if e.get("id") in amendments:
            e = {**e, **amendments[e["id"]]}
        result.append(e)
    return result

"""Config read/write for all shipwright_*_config.json files.

Each skill writes its own config file in the target project root:
  - shipwright_run_config.json
  - shipwright_project_config.json
  - shipwright_plan_config.json
  - shipwright_build_config.json

Config files are the single source of truth for state recovery after
context compaction or /clear.
"""

import json
from pathlib import Path
from typing import Any

CONFIG_FILES = {
    "run": "shipwright_run_config.json",
    "project": "shipwright_project_config.json",
    "plan": "shipwright_plan_config.json",
    "build": "shipwright_build_config.json",
}


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
    """Read all config files. Returns dict keyed by skill name."""
    return {skill: read_config(skill, project_root) for skill in CONFIG_FILES}

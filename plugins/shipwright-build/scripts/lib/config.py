"""Configuration for /shipwright-build.

Reads shipwright_build_config.json from project root.
"""

import json
from pathlib import Path
from typing import Any


CONFIG_NAME = "shipwright_build_config.json"

DEFAULTS = {
    "auto_push": False,
    "conventional_commits": True,
    "decision_log": True,
    "session_handoff": True,
    "migration_safety": True,
}


def load_build_config(project_root: str | Path) -> dict[str, Any]:
    """Load build config with defaults."""
    path = Path(project_root) / CONFIG_NAME
    config = DEFAULTS.copy()
    if path.exists():
        try:
            user_config = json.loads(path.read_text(encoding="utf-8"))
            config.update(user_config)
        except json.JSONDecodeError:
            pass
    return config


def save_build_config(project_root: str | Path, config: dict[str, Any]) -> None:
    """Save build config."""
    path = Path(project_root) / CONFIG_NAME
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

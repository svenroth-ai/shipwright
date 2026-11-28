"""Configuration for /shipwright-build.

Reads shipwright_build_config.json from project root.
"""

import json
from pathlib import Path
from typing import Any
import sys as _sys, pathlib as _pl; _p = str(_pl.Path(__file__).resolve().parents[4] / "shared" / "scripts" / "lib"); _a = _p not in _sys.path; _a and _sys.path.append(_p); import shipwright_paths as _sp; _a and _sys.path.remove(_p)  # noqa: E402


CONFIG_NAME = _sp.rel("build_config")

DEFAULTS = {
    "auto_push": False,
    "conventional_commits": True,
    "decision_log": True,
    "session_handoff": True,
    "migration_safety": True,
}


def load_build_config(project_root: str | Path) -> dict[str, Any]:
    """Load build config with defaults."""
    path = _sp.path("build_config", Path(project_root))
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
    path = _sp.path("build_config", Path(project_root))
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

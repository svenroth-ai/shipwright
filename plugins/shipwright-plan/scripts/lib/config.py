"""Configuration management for /shipwright-plan.

Two config types:
1. Global config: {plugin_root}/config.json (plugin defaults — context, e2e_test_plan, vertex_ai)
2. Session config: {planning_dir}/shipwright_plan_config.json (per-session overrides)

External-review config (models, external_review, llm_client) lives in
shared/config/external_review.json and is read via
``lib.external_review_config.load_review_config`` in shared/scripts/lib.
"""

import json
from pathlib import Path
from typing import Any

GLOBAL_CONFIG_NAME = "config.json"
SESSION_CONFIG_NAME = "shipwright_plan_config.json"


def load_global_config(plugin_root: str | Path) -> dict[str, Any]:
    """Load global plugin config from config.json."""
    path = Path(plugin_root) / GLOBAL_CONFIG_NAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_session_config(planning_dir: str | Path) -> dict[str, Any]:
    """Load session-specific config overrides."""
    path = Path(planning_dir) / SESSION_CONFIG_NAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_session_config(planning_dir: str | Path, config: dict[str, Any]) -> None:
    """Save session-specific config to the planning directory.

    DEPRECATED for shared pipeline state: this writes to {planning_dir}/,
    but shared/scripts/lib/config.py reads from {project_root}/. Use
    write-plan-config.py for pipeline-visible config instead.
    """
    path = Path(planning_dir) / SESSION_CONFIG_NAME
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def get_merged_config(plugin_root: str | Path, planning_dir: str | Path) -> dict[str, Any]:
    """Get merged config (session overrides global)."""
    global_cfg = load_global_config(plugin_root)
    session_cfg = load_session_config(planning_dir)
    return _deep_merge(global_cfg, session_cfg)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dicts, override takes precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def is_e2e_enabled(config: dict[str, Any]) -> bool:
    """Check if E2E test plan generation is enabled."""
    return config.get("e2e_test_plan", {}).get("enabled", True)

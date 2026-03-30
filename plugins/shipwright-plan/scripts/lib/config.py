"""Configuration management for /shipwright-plan.

Two config types:
1. Global config: {plugin_root}/config.json (plugin defaults)
2. Session config: {planning_dir}/shipwright_plan_config.json (per-session overrides)
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure shared lib is importable (use scripts/lib directly to avoid namespace collision)
_shared_lib = Path(__file__).resolve().parents[4] / "shared" / "scripts" / "lib"
sys.path.insert(0, str(_shared_lib))

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
    """Save session-specific config."""
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


def is_external_review_enabled(config: dict[str, Any]) -> bool:
    """Check if external review is enabled and API keys are available."""
    from env import load_shipwright_env
    load_shipwright_env()  # idempotent — ensures .env.local is loaded

    ext = config.get("external_review", {})
    if ext.get("feedback_iterations", 1) == 0:
        return False

    has_openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))

    return has_openrouter or has_gemini or has_openai


def is_e2e_enabled(config: dict[str, Any]) -> bool:
    """Check if E2E test plan generation is enabled."""
    return config.get("e2e_test_plan", {}).get("enabled", True)

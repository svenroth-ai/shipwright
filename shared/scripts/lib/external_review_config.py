"""External review configuration loader (shared across all SDLC plugins).

Provides:
- ``load_review_config(path=None)`` — load shared/config/external_review.json
- ``is_external_review_enabled(config)`` — True iff feedback_iterations > 0 and a key is set
- ``get_external_review_status(config)`` — three-way status: user_disabled | available | missing_keys
- ``resolve_model(config, model_key)`` — resolve a model name with env-var override

Env-var override pattern: ``SHIPWRIGHT_REVIEW_MODEL_<KEY_UPPER>`` overrides
``config['models'][key]``. Empty/whitespace-only values fall back to the config
default. The set of valid keys matches the keys in the shipped config:
``gemini, chatgpt, openrouter_gemini, openrouter_chatgpt``.

This module is the result of consolidating logic that previously lived in
``plugins/shipwright-plan/scripts/lib/config.py``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Make sibling shared/scripts/lib importable so we can pick up `env` (load_shipwright_env).
_SHARED_LIB = Path(__file__).resolve().parent
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

# Default shipping config: shared/config/external_review.json
# parents[0]=lib, [1]=scripts, [2]=shared, then config/external_review.json.
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "external_review.json"

# Whitelist of valid model keys for resolve_model() — matches keys in
# shared/config/external_review.json.
_VALID_MODEL_KEYS: set[str] = {
    "gemini",
    "chatgpt",
    "openrouter_gemini",
    "openrouter_chatgpt",
}

# Env-var prefix for SHIPWRIGHT_REVIEW_MODEL_<KEY_UPPER> overrides.
_ENV_OVERRIDE_PREFIX = "SHIPWRIGHT_REVIEW_MODEL_"


def load_review_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load shared external-review config.

    Returns ``{}`` if the file doesn't exist (graceful degradation).
    """
    path = Path(config_path) if config_path is not None else _DEFAULT_CONFIG_PATH
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def is_external_review_enabled(config: dict[str, Any]) -> bool:
    """Check if external review is enabled and at least one API key is available.

    Considers OPENROUTER_API_KEY, GEMINI_API_KEY/GOOGLE_API_KEY, and OPENAI_API_KEY.
    """
    from env import load_shipwright_env  # type: ignore[import-not-found]

    load_shipwright_env()  # idempotent — ensures .env.local is loaded

    ext = config.get("external_review", {})
    if ext.get("feedback_iterations", 1) == 0:
        return False

    has_openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))

    return has_openrouter or has_gemini or has_openai


def get_external_review_status(config: dict[str, Any]) -> str:
    """Return the three-way review status for the planning/iterate session.

    - ``user_disabled``: feedback_iterations == 0 (explicit opt-out in config).
    - ``available``:    keys present AND feedback_iterations > 0 — review will run.
    - ``missing_keys``: feedback_iterations > 0 but no API key in env.

    Skills branch on this in their Step 5 / equivalent: run review / prompt user / self-review.
    """
    from env import load_shipwright_env  # type: ignore[import-not-found]

    load_shipwright_env()  # idempotent

    ext = config.get("external_review", {})
    if ext.get("feedback_iterations", 1) == 0:
        return "user_disabled"

    has_openrouter = bool(os.environ.get("OPENROUTER_API_KEY"))
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))

    if has_openrouter or has_gemini or has_openai:
        return "available"
    return "missing_keys"


def resolve_model(config: dict[str, Any], model_key: str) -> str:
    """Resolve the model name for ``model_key``, honoring env-var overrides.

    Lookup order:
      1. ``SHIPWRIGHT_REVIEW_MODEL_<KEY_UPPER>`` env var (stripped, must be non-empty)
      2. ``config['models'][model_key]``
      3. ``""`` if neither resolves

    Raises ``ValueError`` if ``model_key`` is not in the whitelist.
    """
    if model_key not in _VALID_MODEL_KEYS:
        raise ValueError(
            f"Invalid model key: {model_key!r}. "
            f"Expected one of: {sorted(_VALID_MODEL_KEYS)}"
        )

    env_value = os.environ.get(f"{_ENV_OVERRIDE_PREFIX}{model_key.upper()}", "").strip()
    if env_value:
        return env_value

    return config.get("models", {}).get(model_key, "")

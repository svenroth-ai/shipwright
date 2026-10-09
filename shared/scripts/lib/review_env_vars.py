"""The framework-level review variables scaffolded into ``.env.local``.

Split out of ``validate_env.py`` (a grandfathered bloat-baseline entry that may
not grow). ``validate_env._SHIPWRIGHT_FRAMEWORK_VARS`` re-exports
``FRAMEWORK_VARS``; the fallback ORDER of the two key vars mirrors
``external_review_config.is_external_review_enabled`` and is locked by
``TestFrameworkOrderDriftProtection``.

The gateway vars (#547) are ``alternative``: the operator-owned route REPLACES
the two keys rather than adding to them. They are scaffolded into NEW files so
the feature is discoverable, and are never reported as a missing key (the adopt
handoff banner would otherwise nag every OpenRouter user for them) nor appended
to an existing file (that would flip "unchanged" to "updated" for users who
never chose the route).
"""

from __future__ import annotations

GATEWAY_BASE_URL_VAR = "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL"


def _gateway_var(name: str, description: str) -> dict:
    return {"name": f"SHIPWRIGHT_REVIEW_GATEWAY_{name}", "description": description,
            "optional": True, "alternative": True}


FRAMEWORK_VARS: list[dict] = [
    {
        "name": "OPENROUTER_API_KEY",
        "description": "OpenRouter API key for external plan/iterate/code reviews "
                       "(required for the ZDR-routed GLM arm)",
        "optional": True,
    },
    {
        "name": "OPENAI_API_KEY",
        "description": "Direct OpenAI API key (alternative to OpenRouter)",
        "optional": True,
    },
    _gateway_var(
        "BASE_URL",
        "https:// base URL of an OpenAI-compatible gateway (Portkey, LiteLLM, ...); when set, "
        "review runs ONLY through it. Extra headers: SHIPWRIGHT_REVIEW_GATEWAY_HEADER_<NAME>=value",
    ),
    *(
        _gateway_var(f"{kind}{slot}", f"Gateway {what} for reviewer slot {slot}")
        for slot in ("1", "2")
        for kind, what in (("MODEL_", "model / virtual-key alias"), ("KEY_MODEL_", "API key"))
    ),
]

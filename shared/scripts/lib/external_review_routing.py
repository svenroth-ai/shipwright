"""Fail-closed OpenRouter routing for ZDR-gated external-review model arms
(DeepSeek, GLM)."""

from __future__ import annotations

from typing import Any

__all__ = [
    "APPROVED_DEEPSEEK_ENDPOINTS",
    "APPROVED_GLM_ENDPOINTS",
    "DeepSeekRoutingPolicyError",
    "GlmRoutingPolicyError",
    "ReviewModelPolicyError",
    "deepseek_openrouter_extra_body",
    "glm_openrouter_extra_body",
    "openrouter_extra_body",
    "resolve_reviewer_model",
]

# Authorization is code-owned. Configuration declares the active ordered
# allowlist and its verification metadata, but cannot bless an arbitrary slug by
# labelling it safe. Adding a verified EU endpoint is deliberately a code +
# config + test review, not an unreviewed project override.
APPROVED_DEEPSEEK_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("novita", "US"),
    ("together", "US"),
)
# Same two vetted providers as DeepSeek's — both also serve GLM 5.3 on
# OpenRouter with an identical zero-retention data policy (verified via
# OpenRouter's own data-policy API, 2026-09-01) — but a SEPARATE code-owned
# constant, not a shared alias: the two families' approved sets are free to
# diverge later without one edit silently relaxing the other.
APPROVED_GLM_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("novita", "US"),
    ("together", "US"),
)
_ALLOWED_REGIONS = frozenset({"US", "EU"})
_REVIEW_MODEL_BINDINGS = {
    ("deepseek", "openrouter"): (
        "openrouter_deepseek",
        "deepseek/deepseek-v4-pro",
    ),
    ("openai", "openrouter"): (
        "openrouter_chatgpt",
        "openai/gpt-5.6-terra",
    ),
    ("openai", "direct"): ("chatgpt", "gpt-5.6-terra"),
}


class DeepSeekRoutingPolicyError(ValueError):
    """The DeepSeek request cannot be routed under the verified ZDR policy."""


class GlmRoutingPolicyError(ValueError):
    """The GLM request cannot be routed under the verified ZDR policy."""


class ReviewModelPolicyError(ValueError):
    """A configured model does not match its declared reviewer identity."""


def resolve_reviewer_model(
    config: dict[str, Any],
    reviewer: str,
    route: str,
    *,
    resolver=None,
) -> str:
    """Resolve and validate the code-owned reviewer/model binding.

    Environment overrides remain visible to the validator but cannot change
    either arm's identity. Validation happens before client construction.
    """
    binding = _REVIEW_MODEL_BINDINGS.get((reviewer, route))
    if binding is None:
        raise ReviewModelPolicyError(
            f"unsupported reviewer route: reviewer={reviewer!r}, route={route!r}"
        )
    model_key, expected = binding
    if resolver is None:
        try:
            from .external_review_config import resolve_model
        except ImportError:  # pragma: no cover - top-level import from tools/
            from external_review_config import resolve_model
        resolver = resolve_model
    resolved = resolver(config, model_key)
    if resolved != expected:
        raise ReviewModelPolicyError(
            f"{reviewer} reviewer on {route} must use {expected!r}; "
            f"configured {resolved!r}"
        )
    return expected


def _configured_endpoints(
    config: dict[str, Any], *, routing_key: str, error_cls: type[ValueError]
) -> list[dict[str, Any]]:
    routing = config.get(routing_key)
    if not isinstance(routing, dict):
        raise error_cls(f"{routing_key} is missing or not an object")
    endpoints = routing.get("provider_allowlist")
    if not isinstance(endpoints, list) or not endpoints:
        raise error_cls(f"{routing_key}.provider_allowlist must be a non-empty list")
    if not all(isinstance(item, dict) for item in endpoints):
        raise error_cls(f"every {routing_key} provider entry must be an object")
    return endpoints


def _provider_openrouter_extra_body(
    config: dict[str, Any],
    *,
    routing_key: str,
    error_cls: type[ValueError],
    approved_endpoints: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    """Return the complete provider policy, or raise before network I/O.

    The shipping configuration must match the code-owned approval registry
    exactly, including order. This makes today's outbound body deterministic
    while keeping the declaration intentionally configurable for a future,
    reviewed US/EU ZDR endpoint addition. Shared by every model family gated
    behind a ZDR provider allowlist — the validation rules are identical,
    only the config section and approval registry differ.
    """
    endpoints = _configured_endpoints(config, routing_key=routing_key, error_cls=error_cls)
    configured: list[tuple[str, str]] = []
    for index, endpoint in enumerate(endpoints):
        slug = endpoint.get("provider")
        region = endpoint.get("region")
        verified = endpoint.get("zero_retention_verified")
        if not isinstance(slug, str) or not slug.strip():
            raise error_cls(f"provider entry {index} has no valid slug")
        if region not in _ALLOWED_REGIONS:
            raise error_cls(f"provider {slug!r} region must be explicitly US or EU")
        if verified is not True:
            raise error_cls(f"provider {slug!r} lacks explicit zero-retention verification")
        configured.append((slug, region))

    if tuple(configured) != approved_endpoints:
        raise error_cls(
            f"configured {routing_key} providers do not exactly match the approved "
            "ordered ZDR endpoint registry"
        )

    providers = [slug for slug, _region in configured]
    return {
        "provider": {
            "only": providers,
            "order": list(providers),
            "allow_fallbacks": False,
            "data_collection": "deny",
            "zdr": True,
        }
    }


def deepseek_openrouter_extra_body(config: dict[str, Any]) -> dict[str, Any]:
    return _provider_openrouter_extra_body(
        config,
        routing_key="deepseek_routing",
        error_cls=DeepSeekRoutingPolicyError,
        approved_endpoints=APPROVED_DEEPSEEK_ENDPOINTS,
    )


def glm_openrouter_extra_body(config: dict[str, Any]) -> dict[str, Any]:
    return _provider_openrouter_extra_body(
        config,
        routing_key="glm_routing",
        error_cls=GlmRoutingPolicyError,
        approved_endpoints=APPROVED_GLM_ENDPOINTS,
    )


def openrouter_extra_body(model_key: str, config: dict[str, Any]) -> dict[str, Any]:
    """Policy for one reviewer identity; never infer an unknown identity."""
    if model_key == "deepseek":
        return deepseek_openrouter_extra_body(config)
    if model_key == "openai":
        return {}
    raise ValueError(f"unknown external reviewer identity: {model_key!r}")

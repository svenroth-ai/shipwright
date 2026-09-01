"""Tests for scripts/lib/pr_review_model_policy.py — the DeepSeek ZDR gate.

Covers the short-circuit (a non-DeepSeek model never loads
shared/config/external_review.json), namespace matching (not exact-string,
which a variant suffix/casing form would bypass — the gap the internal and
external plan reviews both found), and fail-closed propagation on a broken
routing config.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_model_policy as P  # noqa: E402

_SHARED_LIB = Path(__file__).resolve().parents[3] / "shared" / "scripts" / "lib"
sys.path.insert(0, str(_SHARED_LIB))
from external_review_routing import (  # noqa: E402
    APPROVED_DEEPSEEK_ENDPOINTS,
    APPROVED_GLM_ENDPOINTS,
    DeepSeekRoutingPolicyError,
    GlmRoutingPolicyError,
)

_VALID_CONFIG = {
    "deepseek_routing": {
        "provider_allowlist": [
            {"provider": slug, "region": region, "zero_retention_verified": True}
            for slug, region in APPROVED_DEEPSEEK_ENDPOINTS
        ]
    }
}

_VALID_GLM_CONFIG = {
    "glm_routing": {
        "provider_allowlist": [
            {"provider": slug, "region": region, "zero_retention_verified": True}
            for slug, region in APPROVED_GLM_ENDPOINTS
        ]
    }
}


class TestIsDeepseekModel:

    @pytest.mark.parametrize("model", [
        "deepseek/deepseek-v4-pro",
        "deepseek/deepseek-v4-pro:free",
        "DeepSeek/DeepSeek-V4-Pro",
        "  deepseek/deepseek-v4-pro  ",
        "deepseek/deepseek-chat",
    ])
    def test_matches_the_deepseek_namespace(self, model):
        assert P.is_deepseek_model(model) is True

    @pytest.mark.parametrize("model", [
        "anthropic/claude-sonnet-4.6",
        "openai/gpt-5.6-terra",
        "not-deepseek/deepseek-v4-pro",
        "",
    ])
    def test_rejects_everything_else(self, model):
        assert P.is_deepseek_model(model) is False


class TestIsGlmModel:

    @pytest.mark.parametrize("model", [
        "z-ai/glm-5.3",
        "z-ai/glm-5.3:free",
        "Z-AI/GLM-5.3",
        "  z-ai/glm-5.3  ",
        "z-ai/glm-4.6",
    ])
    def test_matches_the_glm_namespace(self, model):
        assert P.is_glm_model(model) is True

    @pytest.mark.parametrize("model", [
        "anthropic/claude-sonnet-4.6",
        "deepseek/deepseek-v4-pro",
        "not-z-ai/glm-5.3",
        "",
    ])
    def test_rejects_everything_else(self, model):
        assert P.is_glm_model(model) is False


class TestResolveExtraBody:

    def test_non_gated_model_returns_empty_without_loading_config(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("must not load config for a non-gated model")
        monkeypatch.setattr(P, "load_review_config", boom)
        assert P.resolve_extra_body("anthropic/claude-sonnet-4.6") == {}

    def test_deepseek_model_returns_the_zdr_body(self, monkeypatch):
        monkeypatch.setattr(P, "load_review_config", lambda: _VALID_CONFIG)
        body = P.resolve_extra_body("deepseek/deepseek-v4-pro")
        assert body["provider"]["only"] == [slug for slug, _ in APPROVED_DEEPSEEK_ENDPOINTS]
        assert body["provider"]["zdr"] is True
        assert body["provider"]["data_collection"] == "deny"

    def test_deepseek_variant_form_also_gets_the_zdr_body(self, monkeypatch):
        monkeypatch.setattr(P, "load_review_config", lambda: _VALID_CONFIG)
        body = P.resolve_extra_body(" DeepSeek/DeepSeek-V4-Pro:free ")
        assert body["provider"]["zdr"] is True

    def test_broken_routing_config_propagates(self, monkeypatch):
        monkeypatch.setattr(P, "load_review_config", lambda: {})
        with pytest.raises(DeepSeekRoutingPolicyError):
            P.resolve_extra_body("deepseek/deepseek-v4-pro")

    def test_glm_model_returns_the_zdr_body(self, monkeypatch):
        monkeypatch.setattr(P, "load_review_config", lambda: _VALID_GLM_CONFIG)
        body = P.resolve_extra_body("z-ai/glm-5.3")
        assert body["provider"]["only"] == [slug for slug, _ in APPROVED_GLM_ENDPOINTS]
        assert body["provider"]["zdr"] is True
        assert body["provider"]["data_collection"] == "deny"

    def test_glm_variant_form_also_gets_the_zdr_body(self, monkeypatch):
        monkeypatch.setattr(P, "load_review_config", lambda: _VALID_GLM_CONFIG)
        body = P.resolve_extra_body(" Z-AI/GLM-5.3:free ")
        assert body["provider"]["zdr"] is True

    def test_broken_glm_routing_config_propagates(self, monkeypatch):
        monkeypatch.setattr(P, "load_review_config", lambda: {})
        with pytest.raises(GlmRoutingPolicyError):
            P.resolve_extra_body("z-ai/glm-5.3")

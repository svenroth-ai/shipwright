"""DeepSeek/OpenAI routing contract. @FR-01.03 @FR-01.11"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import httpx
import pytest

_SHARED = Path(__file__).resolve().parents[1]
for _path in (_SHARED / "scripts" / "tools", _SHARED / "scripts" / "lib"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from external_review_config import load_review_config  # noqa: E402
from external_review_routing import (  # noqa: E402
    APPROVED_DEEPSEEK_ENDPOINTS,
    DeepSeekRoutingPolicyError,
    ReviewModelPolicyError,
    deepseek_openrouter_extra_body,
    resolve_reviewer_model,
)


EXPECTED_PROVIDER = {
    "only": ["novita", "together"],
    "order": ["novita", "together"],
    "allow_fallbacks": False,
    "data_collection": "deny",
    "zdr": True,
}


def test_shipping_config_builds_the_exact_fail_closed_policy():
    config = load_review_config()
    assert APPROVED_DEEPSEEK_ENDPOINTS == (("novita", "US"), ("together", "US"))
    assert deepseek_openrouter_extra_body(config) == {"provider": EXPECTED_PROVIDER}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.pop("deepseek_routing"),
        lambda c: c["deepseek_routing"].update(provider_allowlist=[]),
        lambda c: c["deepseek_routing"]["provider_allowlist"].reverse(),
        lambda c: c["deepseek_routing"]["provider_allowlist"].pop(),
        lambda c: c["deepseek_routing"]["provider_allowlist"].append(
            {"provider": "deepseek", "region": "CN", "zero_retention_verified": True}
        ),
        lambda c: c["deepseek_routing"]["provider_allowlist"][0].update(region="SG"),
        lambda c: c["deepseek_routing"]["provider_allowlist"][0].update(
            zero_retention_verified=False
        ),
        lambda c: c["deepseek_routing"]["provider_allowlist"][0].pop(
            "zero_retention_verified"
        ),
    ],
)
def test_changed_or_unverified_provider_config_fails_closed(mutate):
    config = copy.deepcopy(load_review_config())
    mutate(config)
    with pytest.raises(DeepSeekRoutingPolicyError):
        deepseek_openrouter_extra_body(config)


def test_forbidden_provider_config_stops_before_client_creation(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key")
    import external_review
    import openai

    called = False

    def forbidden_client(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("network client must not be created")

    monkeypatch.setattr(openai, "OpenAI", forbidden_client)
    config = copy.deepcopy(load_review_config())
    config["deepseek_routing"]["provider_allowlist"][0]["region"] = "SG"

    result = external_review.review_with_openrouter(
        "plan", "spec", "system", "{PLAN} {SPEC}", config, "deepseek"
    )

    assert result["status"] == "error"
    assert "region must be explicitly US or EU" in result["reason"]
    assert called is False


@pytest.mark.parametrize(
    "reviewer,route,model_key,forbidden",
    [
        ("deepseek", "openrouter", "openrouter_deepseek", "openai/gpt-5.6-terra"),
        ("openai", "openrouter", "openrouter_chatgpt", "deepseek/deepseek-v4-pro"),
        ("openai", "direct", "chatgpt", "deepseek/deepseek-v4-pro"),
    ],
)
def test_configured_model_cannot_cross_reviewer_identity(
    reviewer, route, model_key, forbidden,
):
    config = copy.deepcopy(load_review_config())
    config["models"][model_key] = forbidden
    with pytest.raises(ReviewModelPolicyError):
        resolve_reviewer_model(config, reviewer, route)


def test_deepseek_override_cannot_travel_through_openai_arm(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key")
    monkeypatch.setenv(
        "SHIPWRIGHT_REVIEW_MODEL_OPENROUTER_CHATGPT",
        "deepseek/deepseek-v4-pro",
    )
    import external_review
    import openai

    called = False

    def forbidden_client(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("network client must not be created")

    monkeypatch.setattr(openai, "OpenAI", forbidden_client)
    result = external_review.review_with_openrouter(
        "plan", "spec", "system", "{PLAN} {SPEC}",
        load_review_config(), "openai",
    )

    assert result["status"] == "error"
    assert "openai reviewer on openrouter must use" in result["reason"]
    assert called is False


def _sdk_transport(monkeypatch, captured: list[dict]):
    import openai

    real_openai = openai.OpenAI

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        model = captured[-1]["model"]
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": model,
                "provider": "NovitaAI",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Review.\nSHIPWRIGHT_VERDICT: approve",
                    },
                    "finish_reason": "stop",
                }],
            },
        )

    def factory(**kwargs):
        kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(handler))
        return real_openai(**kwargs)

    monkeypatch.setattr(openai, "OpenAI", factory)


def test_both_clients_serialize_the_exact_deepseek_request_body(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key")
    import external_review
    import llm_review

    captured: list[dict] = []
    _sdk_transport(monkeypatch, captured)
    config = load_review_config()

    first = external_review.review_with_openrouter(
        "plan", "spec", "system", "{PLAN} {SPEC}", config, "deepseek"
    )
    second = llm_review._review_openrouter(
        "content", "context", "system", "{CONTENT} {CONTEXT}",
        config, "deepseek", 5,
    )

    assert first["status"] == second["status"] == "success"
    assert len(captured) == 2
    for body in captured:
        assert body["model"] == "deepseek/deepseek-v4-pro"
        assert body["provider"] == EXPECTED_PROVIDER
        assert "models" not in body


def test_gpt_openrouter_body_has_no_deepseek_provider_policy(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key")
    import external_review

    captured: list[dict] = []
    _sdk_transport(monkeypatch, captured)
    result = external_review.review_with_openrouter(
        "plan", "spec", "system", "{PLAN} {SPEC}",
        load_review_config(), "openai",
    )

    assert result["status"] == "success"
    assert captured[0]["model"] == "openai/gpt-5.6-terra"
    assert "provider" not in captured[0]
    assert "models" not in captured[0]

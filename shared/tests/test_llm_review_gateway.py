"""The 'gateway' route on shared/scripts/lib/llm_review.py (issue #547).

A 4th, operator-owned route alongside openrouter/direct/none: any
OpenAI-compatible gateway (Portkey, Helicone, LiteLLM proxy, Azure AI
Foundry, ...) reached via ``SHIPWRIGHT_REVIEW_GATEWAY_*`` env vars. Unlike
openrouter/direct it carries NEITHER the model-identity lock
(``external_review_routing.resolve_reviewer_model``) NOR the GLM ZDR
allowlist check — the operator's gateway/virtual key decides which model
answers, by design.

This file covers the ``_review_gateway`` leg in isolation.
``detect_provider`` precedence is in ``test_llm_review_gateway_detect.py``;
``run_review`` aggregation and ``review_verdict`` registration are in
``test_llm_review_gateway_routing.py``. All HTTP is mocked; there is no real
gateway to test against from this repo.
"""

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

_GATEWAY_ENV = (
    "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL",
    "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1",
    "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1",
    "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_2",
    "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_2",
)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content, finish_reason="stop"):
        self.message = _FakeMessage(content)
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, content, model=None, finish_reason="stop"):
        self.choices = [_FakeChoice(content, finish_reason)]
        if model is not None:
            self.model = model


def _make_fake_openai(captured_calls: list, response_factory):
    """A fake ``openai.OpenAI`` that records constructor + create() kwargs."""

    class _FakeCompletions:
        def create(self, **kwargs):
            captured_calls.append({"create_kwargs": kwargs})
            return response_factory()

    class _FakeChatNS:
        completions = _FakeCompletions()

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured_calls.append({"init_kwargs": kwargs})
            self.chat = _FakeChatNS()

    return _FakeOpenAI


def _clear_all_provider_env(monkeypatch):
    for k in (*_GATEWAY_ENV, "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)


# ---------------------------------------------------------------------------
# _review_gateway leg — no identity lock, fail-closed on missing per-slot config
# ---------------------------------------------------------------------------


def test_gateway_leg_missing_model_env_is_error_not_skip(monkeypatch):
    """Once the gateway is selected, a misconfigured slot must fail loudly —
    'skipped' would read as 'review not needed', which is the wrong signal
    for an operator who explicitly opted into gateway-only egress."""
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    import llm_review

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)
    assert result["status"] == "error"
    assert "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1" in result["reason"]


def test_gateway_leg_missing_key_env_is_error(monkeypatch):
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-virtual-model")
    import llm_review

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)
    assert result["status"] == "error"
    assert "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1" in result["reason"]


def test_gateway_leg_accepts_any_model_name_no_identity_lock(monkeypatch):
    """The default routes validate model identity via resolve_reviewer_model
    and reject a drifted value before any client is built. The gateway route
    must NOT do that — the operator's gateway/virtual key decides which
    model actually answers."""
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "whatever-alias-the-operator-picked")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    import llm_review
    import openai

    calls: list = []
    monkeypatch.setattr(
        openai, "OpenAI",
        _make_fake_openai(calls, lambda: _FakeResponse("looks fine", model="resolved/actual-model")),
    )

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)

    assert result["status"] == "success"
    create_kwargs = next(c["create_kwargs"] for c in calls if "create_kwargs" in c)
    assert create_kwargs["model"] == "whatever-alias-the-operator-picked"


def test_gateway_leg_records_answering_model_as_separate_evidence_field(monkeypatch):
    """The role key ('model-1') is just a slot label. The model the gateway
    actually used must be captured separately so the record never implies an
    identity the gateway didn't use."""
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    import llm_review
    import openai

    calls: list = []
    monkeypatch.setattr(
        openai, "OpenAI",
        _make_fake_openai(calls, lambda: _FakeResponse("ok", model="deepseek/deepseek-v4-pro")),
    )

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)
    assert result["answering_model"] == "deepseek/deepseek-v4-pro"


def test_gateway_leg_answering_model_absent_when_response_carries_none(monkeypatch):
    """Not every OpenAI-compatible gateway echoes the resolved model back —
    the field is only ever added when the API actually reported one."""
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    import llm_review
    import openai

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _make_fake_openai(calls, lambda: _FakeResponse("ok")))

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)
    assert "answering_model" not in result


def test_gateway_leg_passes_base_url_and_key_to_client(monkeypatch):
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    import llm_review
    import openai

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _make_fake_openai(calls, lambda: _FakeResponse("ok")))

    llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)

    init_kwargs = next(c["init_kwargs"] for c in calls if "init_kwargs" in c)
    assert init_kwargs["base_url"] == "https://gw.example.com/v1"
    assert init_kwargs["api_key"] == "vk-1"


def test_gateway_arbitrary_headers_pass_through(monkeypatch):
    """SHIPWRIGHT_REVIEW_GATEWAY_HEADER_<NAME> — arbitrarily many, e.g. a WAF
    auth header — must reach the client, generic enough for any
    OpenAI-compatible gateway (no Portkey-specific naming)."""
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_HEADER_X_WAF_TOKEN", "waf-secret")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_HEADER_X_TENANT", "acme")
    import llm_review
    import openai

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _make_fake_openai(calls, lambda: _FakeResponse("ok")))

    llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)

    init_kwargs = next(c["init_kwargs"] for c in calls if "init_kwargs" in c)
    headers = init_kwargs.get("default_headers") or {}
    assert headers["X-WAF-TOKEN"] == "waf-secret"
    assert headers["X-TENANT"] == "acme"


def test_gateway_leg_slot_2_reads_its_own_model_and_key_env_vars(monkeypatch):
    """Every other leg-level test here exercises slot '1' only. A copy/paste
    bug specific to slot 2's f-string interpolation would not be caught by
    any of them — pin slot 2 directly, not via a mocked _review_gateway."""
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_2", "second-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_2", "vk-2")
    import llm_review
    import openai

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _make_fake_openai(calls, lambda: _FakeResponse("ok")))

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "2", 5)

    assert result["status"] == "success"
    init_kwargs = next(c["init_kwargs"] for c in calls if "init_kwargs" in c)
    create_kwargs = next(c["create_kwargs"] for c in calls if "create_kwargs" in c)
    assert init_kwargs["api_key"] == "vk-2"
    assert create_kwargs["model"] == "second-alias"


def test_gateway_leg_api_error_is_error_status(monkeypatch):
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    import llm_review
    import openai

    class _RaisingOpenAI:
        def __init__(self, **_kwargs):
            raise ConnectionError("gateway unreachable")

    monkeypatch.setattr(openai, "OpenAI", _RaisingOpenAI)

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)
    assert result["status"] == "error"
    assert "gateway unreachable" in result["reason"]


def test_gateway_leg_error_message_redacts_key_and_header_secrets(monkeypatch):
    """A misbehaving gateway/proxy that echoes request details back in an
    error body must not leak the API key or header values into `reason` —
    this field can be persisted to disk by a caller (e.g. Adopt's Layer-3
    review writes it into .shipwright/adopt/review.md)."""
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "sk-super-secret-vk-1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_HEADER_X_WAF_TOKEN", "waf-super-secret-token")
    import llm_review
    import openai

    class _RaisingOpenAI:
        def __init__(self, **_kwargs):
            raise ConnectionError(
                "upstream rejected request with headers "
                "{'Authorization': 'Bearer sk-super-secret-vk-1', "
                "'X-WAF-TOKEN': 'waf-super-secret-token'}"
            )

    monkeypatch.setattr(openai, "OpenAI", _RaisingOpenAI)

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)

    assert result["status"] == "error"
    assert "sk-super-secret-vk-1" not in result["reason"]
    assert "waf-super-secret-token" not in result["reason"]
    assert "***redacted***" in result["reason"]

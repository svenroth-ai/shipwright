"""Security-hardening follow-ups from the external plan review on issue #547
(OpenRouter DeepSeek + GPT, --mode iterate): base URL scheme enforcement,
custom-header precedence over the SDK's own Authorization header, and
cross-slot isolation when both legs are configured in the same run.
"""

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)
        self.finish_reason = "stop"


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


def _make_fake_openai(captured_calls: list):
    class _FakeCompletions:
        def create(self, **kwargs):
            captured_calls.append({"create_kwargs": kwargs})
            return _FakeResponse("ok")

    class _FakeChatNS:
        completions = _FakeCompletions()

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured_calls.append({"init_kwargs": kwargs})
            self.chat = _FakeChatNS()

    return _FakeOpenAI


def _clear(monkeypatch):
    for k in (
        "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL",
        "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1",
        "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1",
        "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_2",
        "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_2",
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)


# ---------------------------------------------------------------------------
# base URL scheme — https only, narrow localhost exception
# ---------------------------------------------------------------------------


def test_insecure_http_base_url_is_rejected_before_any_network_call(monkeypatch):
    """Review prompts and the gateway key would otherwise cross the network
    in plaintext. Rejected before the client is even constructed."""
    _clear(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "http://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    import llm_review
    import openai

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _make_fake_openai(calls))

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)

    assert result["status"] == "error"
    assert "https" in result["reason"]
    assert calls == []  # never even attempted a connection


def test_http_localhost_is_allowed_for_local_testing(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "http://localhost:8787/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    import llm_review
    import openai

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _make_fake_openai(calls))

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)

    assert result["status"] == "success"


def test_https_base_url_is_accepted(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    import llm_review
    import openai

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _make_fake_openai(calls))

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)

    assert result["status"] == "success"


# ---------------------------------------------------------------------------
# custom headers can override the SDK's own Authorization header — this is
# what lets a gateway using a non-Bearer scheme (e.g. Azure AI Foundry's
# `api-key` header) be addressed at all, not just add alongside it.
# ---------------------------------------------------------------------------


def test_custom_authorization_header_overrides_the_sdk_generated_one():
    """Uses the REAL openai.OpenAI construction (no fake) to prove header
    precedence via the SDK's own default_headers property — per
    _base_client.py: {**auth_headers, **self._custom_headers}, where custom
    headers are spread last and win. This is what lets a gateway with a
    non-Bearer auth scheme (e.g. Azure AI Foundry's `api-key` header) be
    addressed at all, not just receive an extra header alongside Bearer."""
    import openai

    client = openai.OpenAI(
        api_key="vk-1",
        base_url="https://gw.example.com/v1",
        default_headers={"AUTHORIZATION": "api-key custom-scheme-value"},
    )
    assert client.default_headers["AUTHORIZATION"] == "api-key custom-scheme-value"


# ---------------------------------------------------------------------------
# both slots configured simultaneously — no cross-contamination
# ---------------------------------------------------------------------------


def test_both_slots_configured_together_use_their_own_distinct_values(monkeypatch):
    """A copy/paste bug (e.g. always using slot 1's key, or swapping the two
    slots) would not be caught by a test that only ever configures one slot
    at a time — this configures both, with distinct values, in one run."""
    _clear(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "alias-one")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-one")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_2", "alias-two")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_2", "vk-two")
    import llm_review
    import openai

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _make_fake_openai(calls))

    result_1 = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)
    result_2 = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "2", 5)

    assert result_1["status"] == "success"
    assert result_2["status"] == "success"
    init_calls = [c["init_kwargs"] for c in calls if "init_kwargs" in c]
    create_calls = [c["create_kwargs"] for c in calls if "create_kwargs" in c]
    assert {c["api_key"] for c in init_calls} == {"vk-one", "vk-two"}
    assert {c["model"] for c in create_calls} == {"alias-one", "alias-two"}


def test_insecure_url_error_never_echoes_embedded_credentials(monkeypatch):
    """got {base_url!r} used to include the raw configured URL verbatim — a
    URL with basic-auth userinfo or a token query param would have leaked
    into a persisted error artifact. Must be sanitized, not just redacted
    after the fact, since the rejection message is built before any
    exception (and thus before _redact_secrets) is even involved."""
    _clear(monkeypatch)
    monkeypatch.setenv(
        "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL",
        "http://svenroth:s3cr3t-t0ken@gw.example.com/v1?api_token=another-secret",
    )
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    import llm_review

    result = llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)

    assert result["status"] == "error"
    assert "svenroth" not in result["reason"]
    assert "s3cr3t-t0ken" not in result["reason"]
    assert "another-secret" not in result["reason"]


def test_empty_header_suffix_env_var_is_ignored_not_sent_as_a_blank_header(monkeypatch):
    """SHIPWRIGHT_REVIEW_GATEWAY_HEADER_ with an empty <NAME> suffix would
    otherwise derive an empty header name, which fails at the HTTP layer
    with a confusing error instead of a clear misconfiguration message."""
    _clear(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_HEADER_", "some-value")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_HEADER_X_REAL", "real-value")
    import external_review_gateway

    headers = external_review_gateway.gateway_headers()

    assert "" not in headers
    assert headers == {"X-REAL": "real-value"}


def test_gateway_never_reads_openrouter_or_direct_env_vars(monkeypatch):
    """Not just 'never calls their route functions' — the gateway leg must
    never even READ OPENROUTER_API_KEY/OPENAI_API_KEY, so a value set there
    for the default routes cannot leak into a gateway request by accident."""
    _clear(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "my-alias")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key-must-not-be-used")
    monkeypatch.setenv("OPENAI_API_KEY", "oai-key-must-not-be-used")
    import llm_review
    import openai

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _make_fake_openai(calls))

    llm_review._review_gateway("c", "x", "sys", "u {CONTENT} {CONTEXT}", "1", 5)

    init_kwargs = next(c["init_kwargs"] for c in calls if "init_kwargs" in c)
    assert init_kwargs["api_key"] == "vk-1"
    assert init_kwargs["api_key"] not in ("or-key-must-not-be-used", "oai-key-must-not-be-used")

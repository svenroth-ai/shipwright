"""The gateway leg's token-limit parameter and non-secret evidence (#547).

Split from ``test_external_review_gateway_cli.py``. All HTTP is mocked.
"""

import json
import sys
from pathlib import Path

import pytest

_LIB = str(Path(__file__).resolve().parents[1] / "scripts" / "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

_GATEWAY_ENV = (
    "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL",
    "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1",
    "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1",
    "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_2",
    "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_2",
    "SHIPWRIGHT_REVIEW_GATEWAY_HEADER_CF_ACCESS_CLIENT_ID",
    "SHIPWRIGHT_REVIEW_GATEWAY_HEADER_CF_ACCESS_CLIENT_SECRET",
)


@pytest.fixture
def gateway_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", *_GATEWAY_ENV):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "alias-one")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-secret-1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_2", "alias-two")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_2", "vk-secret-2")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_HEADER_CF_ACCESS_CLIENT_ID", "waf-id-value")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_HEADER_CF_ACCESS_CLIENT_SECRET", "waf-secret-value")


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)
        self.finish_reason = "stop"


class _Resp:
    def __init__(self, content, model):
        self.choices = [_Choice(content)]
        self.model = model


def _fake_openai(calls, rejected_param=None):
    class _Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if rejected_param and rejected_param in kwargs:
                raise RuntimeError(
                    f"Unsupported parameter: '{rejected_param}' is not supported with this model.")
            return _Resp("fine", "actual/model")

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, **kwargs):
            self.chat = _Chat()

    return _Client


@pytest.mark.covers("FR-01.13/AC07")
def test_gateway_leg_sends_max_completion_tokens_first(monkeypatch, gateway_env):
    import openai
    from external_review_gateway import review_gateway_prompt

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(calls))
    result = review_gateway_prompt("p", "sys", "1", 5)

    assert result["status"] == "success"
    assert "max_completion_tokens" in calls[0] and "max_tokens" not in calls[0]
    assert result["gateway_evidence"]["token_param"] == "max_completion_tokens"


@pytest.mark.covers("FR-01.13/AC07")
def test_gateway_leg_falls_back_to_max_tokens_when_rejected(monkeypatch, gateway_env):
    """A gateway fronting an older/non-OpenAI model may not know the newer
    parameter; gpt-5.x rejects the older one - neither is hard-coded."""
    import openai
    from external_review_gateway import review_gateway_prompt

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(calls, rejected_param="max_completion_tokens"))
    result = review_gateway_prompt("p", "sys", "1", 5)

    assert result["status"] == "success"
    assert len(calls) == 2 and "max_tokens" in calls[1]
    assert result["gateway_evidence"]["token_param"] == "max_tokens"


@pytest.mark.covers("FR-01.13/AC07")
def test_gateway_leg_unrelated_error_is_not_retried(monkeypatch, gateway_env):
    import openai
    from external_review_gateway import review_gateway_prompt

    calls: list = []

    class _Boom:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    calls.append(kwargs)
                    raise RuntimeError("401 unauthorized")

        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(openai, "OpenAI", _Boom)
    result = review_gateway_prompt("p", "sys", "1", 5)
    assert result["status"] == "error" and len(calls) == 1
    assert "gateway_evidence" in result


@pytest.mark.covers("FR-01.13/AC07")
def test_gateway_evidence_names_headers_but_never_values(monkeypatch, gateway_env):
    import openai
    from external_review_gateway import review_gateway_prompt

    monkeypatch.setattr(openai, "OpenAI", _fake_openai([]))
    result = review_gateway_prompt("p", "sys", "1", 5)
    evidence = result["gateway_evidence"]

    assert evidence["host"] == "https://gw.example.com"  # host only: no path (may carry ids/tokens)
    assert evidence["header_names"] == ["CF-ACCESS-CLIENT-ID", "CF-ACCESS-CLIENT-SECRET"]
    blob = json.dumps(result)
    for secret in ("vk-secret-1", "vk-secret-2", "waf-id-value", "waf-secret-value"):
        assert secret not in blob


class _ApiError(Exception):
    """Shaped like the SDK's BadRequestError: message + structured code/body."""

    def __init__(self, message, code=None, body=None):
        super().__init__(message)
        self.code, self.body = code, body


def _failing_openai(calls, exc_for):
    class _Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            raise exc_for(kwargs)

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, **kwargs):
            self.chat = _Chat()

    return _Client


@pytest.mark.covers("FR-01.13/AC07")
@pytest.mark.parametrize("exc", [
    # A VALUE error names the parameter but is not "unsupported".
    _ApiError("Error code: 400 - max_completion_tokens is too large: 32000", code="invalid_value"),
    # A gateway that echoes the request kwargs into every error body.
    _ApiError("Error code: 400 - {'type': 'invalid_request_error', 'request': {'max_completion_tokens': 16000}, "
              "'message': 'content filtered'}"),
])
def test_a_400_that_merely_names_the_parameter_is_not_retried(monkeypatch, gateway_env, exc):
    import openai
    from external_review_gateway import review_gateway_prompt

    calls: list = []
    monkeypatch.setattr(openai, "OpenAI", _failing_openai(calls, lambda kw: exc))
    result = review_gateway_prompt("p", "sys", "1", 5)

    assert result["status"] == "error" and len(calls) == 1


@pytest.mark.covers("FR-01.13/AC07")
def test_structured_unsupported_parameter_retries_and_keeps_both_errors(monkeypatch, gateway_env):
    import openai
    from external_review_gateway import review_gateway_prompt

    calls: list = []

    def exc_for(kwargs):
        if "max_completion_tokens" in kwargs:
            return _ApiError("boom-first", code="unsupported_parameter")
        return _ApiError("boom-second")

    monkeypatch.setattr(openai, "OpenAI", _failing_openai(calls, exc_for))
    result = review_gateway_prompt("p", "sys", "1", 5)

    assert len(calls) == 2 and result["status"] == "error"
    assert "boom-first" in result["reason"] and "boom-second" in result["reason"]


@pytest.mark.covers("FR-01.13/AC07")
@pytest.mark.parametrize("unset", [
    "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1",
])
def test_early_failures_still_carry_gateway_evidence(monkeypatch, gateway_env, unset):
    from external_review_gateway import review_gateway_prompt

    monkeypatch.delenv(unset)
    result = review_gateway_prompt("p", "sys", "1", 5)
    assert result["status"] == "error"
    assert result["gateway_evidence"]["host"] == "https://gw.example.com"


@pytest.mark.covers("FR-01.13/AC07")
def test_missing_openai_package_still_carries_gateway_evidence(monkeypatch, gateway_env):
    """The failure #547 actually reported - and the one the record must still explain."""
    import builtins

    from external_review_gateway import review_gateway_prompt

    real_import = builtins.__import__

    def no_openai(name, *a, **k):
        if name == "openai":
            raise ImportError("No module named 'openai'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_openai)
    result = review_gateway_prompt("p", "sys", "1", 5)
    assert result["reason"] == "openai package not installed"
    assert result["gateway_evidence"]["header_names"] == ["CF-ACCESS-CLIENT-ID", "CF-ACCESS-CLIENT-SECRET"]


@pytest.mark.covers("FR-01.13/AC07")
def test_configured_retry_count_reaches_the_client(monkeypatch, gateway_env):
    import openai
    from external_review_gateway import review_gateway_prompt

    seen: dict = {}

    class _Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.chat = type("C", (), {"completions": type("P", (), {
                "create": staticmethod(lambda **kw: _Resp("fine", "m"))})()})()

    monkeypatch.setattr(openai, "OpenAI", _Client)
    review_gateway_prompt("p", "sys", "1", 5, max_retries=4)
    assert seen["max_retries"] == 4


@pytest.mark.covers("FR-01.13/AC07")
def test_evidence_survives_a_malformed_port():
    import external_review_gateway as gw

    evidence = gw.gateway_evidence("https://gw.example.com:abc/v1")

    assert evidence["host"] == "https://gw.example.com"


@pytest.mark.covers("FR-01.13/AC07")
@pytest.mark.parametrize("code,message,expected", [
    ("unsupported_value", "Unsupported value: 'max_completion_tokens' does not support 32000", False),
    ("unsupported_parameter", "Unsupported parameter: 'max_completion_tokens'", True),
])
def test_a_structured_code_decides_the_retry(code, message, expected):
    import external_review_gateway as gw

    class Err(Exception):
        pass

    exc = Err(message)
    exc.code = code
    assert gw._token_param_rejected(exc) is expected


@pytest.mark.covers("FR-01.13/AC07")
def test_insecure_url_with_malformed_port_still_returns_an_error_with_evidence(gateway_env, monkeypatch):
    import external_review_gateway as gw

    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "http://gw.example.com:abc/v1")
    result = gw.review_gateway_prompt("p", "s", "1", 5)

    assert result["status"] == "error"
    assert "gateway_evidence" in result


@pytest.mark.covers("FR-01.13/AC07")
def test_a_generic_error_code_with_unsupported_wording_still_falls_back():
    import external_review_gateway as gw

    class Err(Exception):
        code = "invalid_request_error"

    assert gw._token_param_rejected(Err("Unsupported parameter: 'max_completion_tokens'; use max_tokens")) is True


@pytest.mark.covers("FR-01.13/AC07")
def test_error_evidence_always_has_a_token_param_key(gateway_env, monkeypatch):
    import external_review_gateway as gw

    monkeypatch.delenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", raising=False)
    result = gw.review_gateway_prompt("p", "s", "1", 5)

    assert result["status"] == "error"
    assert result["gateway_evidence"]["token_param"] is None

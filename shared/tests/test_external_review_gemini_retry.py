"""Retry eligibility for the direct-Gemini reasoning fallback."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
sys.path.insert(0, str(_LIB))

from external_review_degraded import _is_http_400, gemini_generate  # noqa: E402


class _StatusError(RuntimeError):
    def __init__(self, status_code):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


def test_only_http_400_is_a_provider_retry_signal():
    assert _is_http_400(_StatusError(400))
    for exc in (
        AttributeError(), TypeError(), ValueError(),
        TimeoutError(), ConnectionError(), RuntimeError(),
        _StatusError(401), _StatusError(403), _StatusError(429), _StatusError(500),
    ):
        assert not _is_http_400(exc)


class _Types:
    class ThinkingConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)


class _Genai:
    types = _Types


class _Models:
    def __init__(self, failures):
        self.failures = iter(failures)
        self.calls = 0

    def generate_content(self, **_kwargs):
        self.calls += 1
        failure = next(self.failures)
        if failure:
            raise failure
        return object()


class _Client:
    def __init__(self, failures):
        self.models = _Models(failures)


def test_network_timeout_is_not_retried():
    client = _Client([TimeoutError("slow")])
    with pytest.raises(TimeoutError, match="slow"):
        gemini_generate(_Genai, client, "model", "prompt", "system")
    assert client.models.calls == 1


def test_failed_fallback_preserves_both_attempt_errors():
    client = _Client([_StatusError(400), RuntimeError("fallback failed")])
    with pytest.raises(RuntimeError) as caught:
        gemini_generate(_Genai, client, "model", "prompt", "system")
    message = str(caught.value)
    assert "status 400" in message
    assert "fallback failed" in message
    assert client.models.calls == 2

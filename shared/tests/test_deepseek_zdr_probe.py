"""Synthetic live probe is policy-identical and evidence-safe. @FR-01.03"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import probe_deepseek_zdr  # noqa: E402
from external_review_config import load_review_config  # noqa: E402


class _Message:
    content = "ZDR_PROBE_OK"


class _Choice:
    message = _Message()
    finish_reason = "stop"


class _Response:
    choices = [_Choice()]
    provider = "NovitaAI"


def _fake_openai(monkeypatch, outcome):
    import openai

    class Completions:
        def create(self, **kwargs):
            if isinstance(outcome, Exception):
                raise outcome
            outcome.update(kwargs)
            return _Response()

    class Client:
        def __init__(self, **_kwargs):
            self.chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr(openai, "OpenAI", Client)


def test_missing_credential_is_an_explicit_skip(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    payload = probe_deepseek_zdr.run_probe(load_review_config(), api_key=None)
    assert payload["status"] == "skipped"
    assert payload["reason"] == "openrouter_credential_unavailable"
    assert payload["live_request_sent"] is False


def test_probe_reuses_the_production_policy_and_records_no_secret(monkeypatch):
    captured: dict = {}
    _fake_openai(monkeypatch, captured)
    secret = "sk-or-secret-that-must-not-survive"
    payload = probe_deepseek_zdr.run_probe(load_review_config(), api_key=secret)

    assert payload["status"] == "success"
    assert payload["selected_provider"] == "novita"
    assert captured["model"] == "deepseek/deepseek-v4-pro"
    assert captured["extra_body"] == {
        "provider": {
            "only": ["novita", "together"],
            "order": ["novita", "together"],
            "allow_fallbacks": False,
            "data_collection": "deny",
            "zdr": True,
        }
    }
    evidence = json.dumps(payload)
    assert secret not in evidence
    for forbidden in ("authorization", "headers", "request_body", "response_body"):
        assert forbidden not in evidence.lower()


def test_unlisted_selected_provider_degrades_the_probe(monkeypatch):
    captured: dict = {}
    _fake_openai(monkeypatch, captured)
    monkeypatch.setattr(_Response, "provider", "DeepSeek")
    payload = probe_deepseek_zdr.run_probe(load_review_config(), api_key="secret")
    assert payload["status"] == "degraded"
    assert payload["reason"] == "selected_provider_not_approved"


def test_probe_exception_is_reduced_to_a_safe_error_class(monkeypatch):
    _fake_openai(monkeypatch, RuntimeError("Authorization: Bearer secret-value"))
    payload = probe_deepseek_zdr.run_probe(load_review_config(), api_key="secret-value")
    assert payload["status"] == "degraded"
    assert payload["reason"] == "openrouter_request_failed"
    assert payload["error_type"] == "RuntimeError"
    assert payload["live_request_attempted"] is True
    assert payload["live_request_sent"] is False
    assert "secret-value" not in json.dumps(payload)


def test_probe_client_construction_failure_does_not_claim_request_sent(monkeypatch):
    import openai

    def fail_before_request(**_kwargs):
        raise RuntimeError("constructor failed")

    monkeypatch.setattr(openai, "OpenAI", fail_before_request)
    payload = probe_deepseek_zdr.run_probe(load_review_config(), api_key="secret")

    assert payload["status"] == "degraded"
    assert payload["live_request_attempted"] is False
    assert payload["live_request_sent"] is False

"""Synthetic live probe for the PR-review gate's GLM arm is policy-identical
and evidence-safe. Mirrors shared/tests/test_deepseek_zdr_probe.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
_TOOLS = PLUGIN_ROOT / "scripts" / "tools"
_PLUGIN_LIB = PLUGIN_ROOT / "scripts" / "lib"
_SHARED_LIB = PLUGIN_ROOT.parents[1] / "shared" / "scripts" / "lib"
for _path in (_TOOLS, _PLUGIN_LIB, _SHARED_LIB):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import probe_glm_zdr  # noqa: E402
from external_review_config import load_review_config  # noqa: E402

# Deliberately NOT in any real credential format (no `sk-`/`ghp_`/`xox` prefix) so the
# repo's secret-scan hooks don't flag this synthetic fixture.
FAKE_KEY = "ORTESTKEY-not-a-real-credential-0123456789"


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


def test_selected_provider_reads_the_model_extra_fallback():
    class _Extra:
        provider = None
        model_extra = {"provider": "TogetherAI"}

    assert probe_glm_zdr._selected_provider(_Extra()) == "together"


def test_selected_provider_returns_none_for_an_unrecognized_shape():
    class _NoProvider:
        provider = None
        model_extra = None

    assert probe_glm_zdr._selected_provider(_NoProvider()) is None


def test_broken_routing_config_degrades_before_any_request():
    payload = probe_glm_zdr.run_probe({}, api_key="unused")
    assert payload["status"] == "degraded"
    assert payload["reason"] == "glm_routing_policy_invalid"
    assert payload["live_request_sent"] is False
    assert payload["live_request_attempted"] is False


def test_missing_credential_is_an_explicit_skip(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    payload = probe_glm_zdr.run_probe(load_review_config(), api_key=None)
    assert payload["status"] == "skipped"
    assert payload["reason"] == "openrouter_credential_unavailable"
    assert payload["live_request_sent"] is False


def test_probe_reuses_the_production_policy_and_records_no_secret(monkeypatch):
    captured: dict = {}
    _fake_openai(monkeypatch, captured)
    payload = probe_glm_zdr.run_probe(load_review_config(), api_key=FAKE_KEY)

    assert payload["status"] == "success"
    assert payload["selected_provider"] == "novita"
    assert captured["model"] == "z-ai/glm-5.3"
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
    assert FAKE_KEY not in evidence
    for forbidden in ("authorization", "headers", "request_body", "response_body"):
        assert forbidden not in evidence.lower()


def test_unlisted_selected_provider_degrades_the_probe(monkeypatch):
    captured: dict = {}
    _fake_openai(monkeypatch, captured)
    monkeypatch.setattr(_Response, "provider", "DeepSeek")
    payload = probe_glm_zdr.run_probe(load_review_config(), api_key=FAKE_KEY)
    assert payload["status"] == "degraded"
    assert payload["reason"] == "selected_provider_not_approved"


def test_probe_exception_is_reduced_to_a_safe_error_class(monkeypatch):
    _fake_openai(monkeypatch, RuntimeError(f"Authorization: Bearer {FAKE_KEY}"))
    payload = probe_glm_zdr.run_probe(load_review_config(), api_key=FAKE_KEY)
    assert payload["status"] == "degraded"
    assert payload["reason"] == "openrouter_request_failed"
    assert payload["error_type"] == "RuntimeError"
    assert payload["live_request_attempted"] is True
    assert payload["live_request_sent"] is False
    assert FAKE_KEY not in json.dumps(payload)


def test_probe_client_construction_failure_does_not_claim_request_sent(monkeypatch):
    import openai

    def fail_before_request(**_kwargs):
        raise RuntimeError("constructor failed")

    monkeypatch.setattr(openai, "OpenAI", fail_before_request)
    payload = probe_glm_zdr.run_probe(load_review_config(), api_key=FAKE_KEY)

    assert payload["status"] == "degraded"
    assert payload["live_request_attempted"] is False
    assert payload["live_request_sent"] is False


class TestMain:

    def test_writes_evidence_and_exits_zero_on_a_skip(self, monkeypatch, tmp_path):
        # No credential in the environment: run_probe returns "skipped", not
        # "degraded" — main() must still write the evidence file and exit 0.
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setattr(probe_glm_zdr, "load_shipwright_env", lambda _root: None)
        monkeypatch.setattr(
            probe_glm_zdr, "load_review_config", lambda project_root=None: load_review_config())
        monkeypatch.setattr(
            sys, "argv",
            ["probe_glm_zdr.py", "--project-root", str(tmp_path), "--run-id", "test-run"])

        exit_code = probe_glm_zdr.main()

        assert exit_code == 0
        evidence = tmp_path / ".shipwright" / "planning" / "iterate" / "test-run" / "glm-zdr-probe.json"
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        assert payload["status"] == "skipped"

    def test_unsafe_run_id_is_rejected_before_any_config_load(self, monkeypatch, tmp_path):
        def boom(*_a, **_k):
            raise AssertionError("must not load config for a rejected run id")
        monkeypatch.setattr(probe_glm_zdr, "load_shipwright_env", boom)
        monkeypatch.setattr(
            sys, "argv",
            ["probe_glm_zdr.py", "--project-root", str(tmp_path), "--run-id", "../escape"])

        with pytest.raises(SystemExit):
            probe_glm_zdr.main()

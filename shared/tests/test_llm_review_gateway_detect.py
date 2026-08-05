"""``detect_provider``'s gateway precedence (issue #547) — split out of
test_llm_review_gateway.py, which now covers the ``_review_gateway`` leg in
isolation; run_review aggregation and review_verdict registration are in
test_llm_review_gateway_routing.py.

Fail-closed is the property under test: a configured gateway
(``SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL`` set) must win even when the
openrouter/direct keys are ALSO present — this is not just a priority
order, it is what keeps a gateway-only egress policy from being silently
bypassed.
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


def _clear_all_provider_env(monkeypatch):
    for k in (*_GATEWAY_ENV, "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_detect_provider_returns_gateway_when_base_url_set(monkeypatch):
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    import llm_review

    assert llm_review.detect_provider() == "gateway"


def test_detect_provider_prefers_gateway_over_openrouter_and_direct(monkeypatch):
    """A configured gateway wins even when the default-route keys are ALSO set —
    this is the fail-closed egress-policy property, not just a priority order."""
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
    import llm_review

    assert llm_review.detect_provider() == "gateway"


def test_detect_provider_falls_back_normally_without_gateway_configured(monkeypatch):
    """Regression: default openrouter/direct/none chain is unchanged."""
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    import llm_review

    assert llm_review.detect_provider() == "openrouter"

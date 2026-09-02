"""``run_review`` aggregation and ``review_verdict`` registration for the
'gateway' route (issue #547) — split out of test_llm_review_gateway.py,
which covers ``detect_provider``/``_review_gateway`` in isolation.

The load-bearing property here is fail-closed: once
``SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL`` is configured, a gateway leg failure
must never silently fall back to openrouter or direct, even when those
keys are also present — a silent fallback would violate the operator's
egress policy, not merely be an inconvenience.
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


# ---------------------------------------------------------------------------
# run_review — fail-closed: gateway failure never silently falls back
# ---------------------------------------------------------------------------


def test_run_review_gateway_success_uses_model_1_model_2_role_pair(monkeypatch):
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "alias-1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_2", "alias-2")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_2", "vk-2")
    import llm_review

    expected = {"status": "success", "feedback": "review"}
    monkeypatch.setattr(llm_review, "_review_gateway", lambda *_a: expected)

    result = llm_review.run_review("content", "context")

    assert result["provider"] == "gateway"
    assert result["success"] is True
    assert set(result["reviews"]) == {"model-1", "model-2"}
    assert result["reviews"]["model-1"] == expected
    assert result["reviews"]["model-2"] == expected


def test_run_review_gateway_fallback_catch_also_redacts_secrets(monkeypatch):
    """review_gateway() redacts internally; this pins the second, defense-in-
    depth layer — run_review's own except around future.result() — in case
    _review_gateway ever raises past its own try/except (not reachable
    today, but a silent leak here would ship without a test to catch it)."""
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "sk-outer-secret-1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_HEADER_X_WAF_TOKEN", "waf-outer-secret")
    import llm_review

    def _raises_past_its_own_handling(*_a, **_kw):
        raise RuntimeError("upstream said: Bearer sk-outer-secret-1 / X-WAF-TOKEN waf-outer-secret")

    monkeypatch.setattr(llm_review, "_review_gateway", _raises_past_its_own_handling)

    result = llm_review.run_review("content", "context")

    reason_1 = result["reviews"]["model-1"]["reason"]
    assert "sk-outer-secret-1" not in reason_1
    assert "waf-outer-secret" not in reason_1
    assert "***redacted***" in reason_1


def test_run_review_gateway_failure_never_falls_back_to_openrouter_or_direct(monkeypatch):
    """The rationale is explicit: when an egress policy requires all traffic
    through the gateway, a silent fallback to a direct/openrouter API call is
    a policy violation, not a convenience."""
    _clear_all_provider_env(monkeypatch)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    # Deliberately leave MODEL_1/MODEL_2 unset so both legs fail closed.
    # ALSO set the default-route keys to prove they are never touched.
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENAI_API_KEY", "oai-key")
    import llm_review

    def _boom(*_args, **_kwargs):
        raise AssertionError("must not call the openrouter/direct route when gateway is configured")

    monkeypatch.setattr(llm_review, "_review_openrouter", _boom)
    monkeypatch.setattr(llm_review, "_review_openai", _boom)

    result = llm_review.run_review("content", "context")

    assert result["provider"] == "gateway"
    assert result["success"] is False
    # Exact key set, not just presence: if _review_openrouter/_review_openai
    # were ever accidentally invoked too, _boom's AssertionError would land
    # under "deepseek"/"openai" keys that a presence-only check never looks
    # at, and this test would keep passing through the regression it exists
    # to catch.
    assert set(result["reviews"]) == {"model-1", "model-2"}
    assert result["reviews"]["model-1"]["status"] == "error"
    assert result["reviews"]["model-2"]["status"] == "error"


# ---------------------------------------------------------------------------
# review_verdict — the new pair is registered, not aliased onto glm/openai
# ---------------------------------------------------------------------------


def test_gateway_reviewer_pair_is_registered_in_review_verdict():
    from lib.review_verdict import GATEWAY_REVIEWERS, summarize_reviews

    assert GATEWAY_REVIEWERS == ("model-1", "model-2")
    reviews = {
        "model-1": {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: approve"},
        "model-2": {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: reject"},
    }
    out = summarize_reviews(reviews)
    assert out["verdicts"] == {"model-1": "approve", "model-2": "reject"}
    assert out["contradiction"]["detected"] is True
    assert out["contradiction"]["comparable"] is True


def test_glm_openai_and_historical_pairs_still_supported():
    """Additive registration must not disturb the existing pairs."""
    from lib.review_verdict import summarize_reviews

    current = summarize_reviews({
        "glm": {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: approve"},
        "openai": {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: approve"},
    })
    assert current["contradiction"]["reason"].startswith("verdicts agree")

    historical_deepseek = summarize_reviews({
        "deepseek": {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: approve"},
        "openai": {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: approve"},
    })
    assert historical_deepseek["contradiction"]["reason"].startswith("verdicts agree")

    historical_gemini = summarize_reviews({
        "gemini": {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: approve"},
        "openai": {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: approve"},
    })
    assert historical_gemini["contradiction"]["reason"].startswith("verdicts agree")

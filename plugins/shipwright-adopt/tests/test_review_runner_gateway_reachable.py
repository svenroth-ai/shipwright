"""The gateway route must be reachable from its named consumer (issue #547).

``review_runner._has_any_api_key()`` gates whether Layer-3 review runs at
all *before* ``llm_review`` is even imported. It used to check only
OPENROUTER_API_KEY/OPENAI_API_KEY — an operator who configures *only* a
gateway (the exact scenario this feature targets: an egress policy that
forbids direct OpenRouter/OpenAI calls) would have this gate skip Layer-3
review before ``llm_review.detect_provider()`` ever runs, making the
gateway route unreachable from Adopt. Caught by code review; pinned here.
"""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import review_runner  # noqa: E402

_SNAPSHOT = {"profile": {"matched": "python"}, "features": [], "stack": {}}


def _install_fake_llm_review(monkeypatch, result: dict):
    fake = type(sys)("llm_review")
    fake.run_review = lambda *_a, **_kw: result  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llm_review", fake)


def test_gateway_only_env_does_not_skip_before_llm_review_runs(monkeypatch, tmp_path):
    for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    _install_fake_llm_review(monkeypatch, {
        "success": True,
        "provider": "gateway",
        "reviews": {
            "model-1": {"status": "success", "feedback": "looks fine", "via": "gateway"},
            "model-2": {"status": "success", "feedback": "looks fine", "via": "gateway"},
        },
    })

    got = review_runner.run_review(tmp_path, snapshot=_SNAPSHOT)

    assert got["status"] == "completed"
    assert got["reason"] != "no_api_key"
    assert got["provider"] == "gateway"


def test_no_provider_configured_at_all_still_skips(monkeypatch, tmp_path):
    """Regression: the widened gate must not become 'always run'."""
    for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL"):
        monkeypatch.delenv(k, raising=False)

    got = review_runner.run_review(tmp_path, snapshot=_SNAPSHOT)

    assert got["status"] == "skipped"
    assert got["reason"] == "no_api_key"

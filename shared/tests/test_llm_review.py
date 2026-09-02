"""AC1 regression for shared/scripts/lib/llm_review.py (the other live
OpenAI review script, used by adopt Layer-3 review + review_assistant_ui_plan).

Same incompatible-param bug as external_review.py: the direct OpenAI call
must send ``max_completion_tokens`` (gpt-5.x rejects ``max_tokens``). Also
locks in that ``run_review`` already reports ``success`` honestly — it is
``False`` when no leg succeeds, so it never silently no-ops, and that
``DEFAULT_MODELS`` does not drift from the shipping config.
"""

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from external_review_degraded import DEFAULT_TIMEOUT_SECONDS, MAX_OUTPUT_TOKENS  # noqa: E402


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


def _make_fake_openai(captured: dict):
    class _FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeResponse("LLM_REVIEW_OK")

    class _FakeChatNS:
        completions = _FakeCompletions()

    class _FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = _FakeChatNS()

    return _FakeOpenAI


def test_llm_review_openai_uses_max_completion_tokens(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    import llm_review
    import openai

    captured: dict = {}
    monkeypatch.setattr(openai, "OpenAI", _make_fake_openai(captured))

    result = llm_review._review_openai(
        "CONTENT", "CONTEXT", "system", "u {CONTENT} {CONTEXT}",
        {"models": {"chatgpt": "gpt-5.6-terra"}}, 5,
    )

    assert result["status"] == "success"
    assert "max_tokens" not in captured
    assert captured.get("max_completion_tokens") == MAX_OUTPUT_TOKENS


def test_run_review_success_is_false_when_no_leg_succeeds(monkeypatch):
    """llm_review's aggregate success must be honest — no silent no-op.

    With no keys at all, both legs skip and success must be False (unlike
    external_review.py's old hardcoded success:true bug)."""
    for k in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    import llm_review

    result = llm_review.run_review("content", "context")
    assert result["provider"] == "none"
    assert result["success"] is False
    assert result["partial"] is False
    assert result["warnings"] == []


def test_run_review_direct_openai_marks_glm_unavailable(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    import llm_review

    expected = {"status": "success", "feedback": "review"}
    monkeypatch.setattr(llm_review, "_review_openai", lambda *_args: expected)

    result = llm_review.run_review("content", "context")

    assert result["provider"] == "direct"
    assert result["success"] is True
    assert result["partial"] is True
    assert result["reviews"]["glm"] == {
        "status": "skipped",
        "reason": "GLM requires an approved OpenRouter ZDR endpoint",
    }
    assert result["reviews"]["openai"] == expected
    assert result["warnings"] == ["glm: reviewer arm skipped"]


def test_one_usable_leg_keeps_success_but_marks_the_result_partial(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    import llm_review

    def _leg(*_args):
        model_key = _args[-2]
        if model_key == "glm":
            return {"status": "success", "feedback": "review"}
        return {"status": "degraded", "feedback": "partial", "reason": "cut off"}

    monkeypatch.setattr(llm_review, "_review_openrouter", _leg)
    result = llm_review.run_review("content", "context")

    assert result["success"] is True
    assert result["partial"] is True
    assert result["warnings"] == ["openai: reviewer arm degraded"]


def test_one_error_leg_is_partial_and_names_the_unavailable_arm(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    import llm_review

    def _leg(*_args):
        model_key = _args[-2]
        if model_key == "glm":
            return {"status": "error", "reason": "routing unavailable"}
        return {"status": "success", "feedback": "review"}

    monkeypatch.setattr(llm_review, "_review_openrouter", _leg)
    result = llm_review.run_review("content", "context")

    assert result["success"] is True
    assert result["partial"] is True
    assert result["warnings"] == ["glm: reviewer arm error"]


def test_default_models_match_shipping_config():
    """DEFAULT_MODELS must not drift from shared/config/external_review.json.

    llm_review falls back to DEFAULT_MODELS whenever a caller passes no
    ``models`` dict, while external_review.py resolves the same keys from the
    shipping config. If the two disagree, two callers reviewing the same diff
    silently use different models. Both sources have now been hand-edited in
    lockstep twice (gpt-5.4 -> terra-pro, terra-pro -> terra) — pin the
    invariant instead of relying on the next editor remembering."""
    import llm_review
    from external_review_config import load_review_config

    shipped = {
        key: value
        for key, value in load_review_config()["models"].items()
        if not key.startswith("_")
    }
    assert llm_review.DEFAULT_MODELS == shipped


def test_default_timeout_matches_shipping_config():
    """The two paths must wait the same length of time.

    `external_review.py` reads `llm_client.timeout_seconds` from the shipping
    config; `llm_review.run_review` takes a default parameter, and adopt never
    passes one. Same drift shape as `test_default_models_match_shipping_config`
    above — and newly load-bearing, because this change raised the output budget
    4x, which raised generation time (measured 89.2s for a 10500-token
    completion). A path left at the old 120s would turn a slow-but-complete
    review into a timeout that returns nothing.
    """
    import inspect

    import llm_review
    from external_review_config import load_review_config

    shipped = load_review_config()["llm_client"]["timeout_seconds"]
    assert DEFAULT_TIMEOUT_SECONDS == shipped
    default = inspect.signature(llm_review.run_review).parameters["timeout"].default
    assert default == shipped

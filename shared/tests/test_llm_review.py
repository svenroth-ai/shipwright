"""AC1 regression for shared/scripts/lib/llm_review.py (the other live
OpenAI review script, used by adopt Layer-3 review + review_assistant_ui_plan).

Same incompatible-param bug as external_review.py: the direct OpenAI call
must send ``max_completion_tokens`` (gpt-5.x rejects ``max_tokens``). Also
locks in that ``run_review`` already reports ``success`` honestly — it is
``False`` when no leg succeeds, so it never silently no-ops.
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
        {"chatgpt": "gpt-5.4"}, 5,
    )

    assert result["status"] == "success"
    assert "max_tokens" not in captured
    assert captured.get("max_completion_tokens") == 4096


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

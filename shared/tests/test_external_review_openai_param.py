"""AC1 regression: direct OpenAI review must use max_completion_tokens.

gpt-5.x on the direct OpenAI Chat Completions API rejects ``max_tokens`` with
an 'Unsupported parameter' 400 — the exact incompatible param that silently
degraded the live review gate in SS6. The fix swaps it for
``max_completion_tokens`` (universally supported on current chat models). The
OpenRouter path keeps ``max_tokens`` on purpose: OpenRouter normalises it
downstream, and its documented request field is ``max_tokens``.
"""

import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


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
    """Fake ``openai.OpenAI`` class that records the create() kwargs."""

    class _FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeResponse("REVIEW_OK")

    class _FakeChatNS:
        completions = _FakeCompletions()

    class _FakeOpenAI:
        def __init__(self, **_kwargs):
            self.chat = _FakeChatNS()

    return _FakeOpenAI


def test_review_with_openai_uses_max_completion_tokens(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    for k in ("SHIPWRIGHT_REVIEW_MODEL_CHATGPT",):
        monkeypatch.delenv(k, raising=False)

    import external_review
    import openai

    captured: dict = {}
    monkeypatch.setattr(openai, "OpenAI", _make_fake_openai(captured))

    config = {"models": {"chatgpt": "gpt-5.4"}, "llm_client": {"timeout_seconds": 5}}
    result = external_review.review_with_openai(
        "PLAN_BODY", "SPEC_BODY", "system", "user {SPEC} {PLAN}", config
    )

    assert result["status"] == "success"
    assert result["feedback"] == "REVIEW_OK"
    # The incompatible param must be gone; the correct one must be present.
    assert "max_tokens" not in captured
    assert captured.get("max_completion_tokens") == 4096

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

_SHARED = Path(__file__).resolve().parents[1]
for _p in (_SHARED / "scripts" / "tools", _SHARED / "scripts" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from external_review_degraded import MAX_OUTPUT_TOKENS  # noqa: E402


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
    # Budget itself is pinned by test_external_review_budget.py; this asserts
    # the arm draws from the shared constant rather than a literal of its own.
    assert captured.get("max_completion_tokens") == MAX_OUTPUT_TOKENS

"""Budget, timeout, and reply parity across both live review clients."""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
for _path in (_SHARED / "scripts" / "lib", _SHARED / "scripts" / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from external_review_config import load_review_config  # noqa: E402
from external_review_degraded import (  # noqa: E402
    DEFAULT_TIMEOUT_SECONDS,
    MAX_OUTPUT_TOKENS,
)


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content, finish_reason):
        self.message = _Message(content)
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, content, finish_reason):
        self.choices = [_Choice(content, finish_reason)]


def _fake_openai(captured: dict, content="REVIEW_BODY", finish_reason="stop"):
    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Response(content, finish_reason)

    class Client:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = type("Chat", (), {"completions": Completions()})()

    return Client


def _call_both_openrouter(monkeypatch, content, finish_reason):
    import openai
    import external_review
    import llm_review

    config = load_review_config()
    first_capture: dict = {}
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(
        first_capture, content, finish_reason
    ))
    first = llm_review._review_openrouter(
        "content", "context", "system", "{CONTENT} {CONTEXT}",
        config, "deepseek", 5,
    )
    second_capture: dict = {}
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(
        second_capture, content, finish_reason
    ))
    second = external_review.review_with_openrouter(
        "plan", "spec", "system", "{PLAN} {SPEC}",
        config, "deepseek",
    )
    return (first, first_capture), (second, second_capture)


def test_openrouter_arms_agree_on_budget_and_policy(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    (_, first), (_, second) = _call_both_openrouter(
        monkeypatch, "REVIEW_BODY", "stop"
    )
    assert first["max_tokens"] == second["max_tokens"] == MAX_OUTPUT_TOKENS
    assert first["extra_body"] == second["extra_body"]


def test_direct_openai_arms_agree_on_budget(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    import openai
    import external_review
    import llm_review

    config = load_review_config()
    captures = []
    for call in (
        lambda: llm_review._review_openai(
            "content", "context", "system", "user", config, 5
        ),
        lambda: external_review.review_with_openai(
            "plan", "spec", "system", "user", config
        ),
    ):
        captured: dict = {}
        captures.append(captured)
        monkeypatch.setattr(openai, "OpenAI", _fake_openai(captured))
        assert call()["status"] == "success"
    for captured in captures:
        assert "max_tokens" not in captured
        assert captured["max_completion_tokens"] == MAX_OUTPUT_TOKENS


def test_clients_default_to_the_shared_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    import openai
    import external_review

    config = load_review_config()
    config.pop("llm_client")
    captured: dict = {}
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(captured))
    assert external_review.review_with_openai(
        "plan", "spec", "system", "user", config
    )["status"] == "success"
    assert captured["client_kwargs"]["timeout"] == DEFAULT_TIMEOUT_SECONDS


def test_both_paths_degrade_truncated_and_empty_replies(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    for content, finish_reason in (("partial", "length"), ("", "stop")):
        (first, _), (second, _) = _call_both_openrouter(
            monkeypatch, content, finish_reason
        )
        assert first["status"] == second["status"] == "degraded"


def test_complete_reply_remains_success(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    (first, _), (second, _) = _call_both_openrouter(
        monkeypatch, "real review", "stop"
    )
    assert first["status"] == second["status"] == "success"


def test_run_review_is_false_when_every_leg_degrades(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    import openai
    import llm_review

    monkeypatch.setattr(
        openai, "OpenAI", _fake_openai({}, "cut off", "length")
    )
    result = llm_review.run_review("content", "context")
    assert result["success"] is False
    assert {review["status"] for review in result["reviews"].values()} == {
        "degraded"
    }

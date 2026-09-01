"""Retry-on-empty-reply for the external-review OpenRouter/OpenAI call path.

Root cause (iterate-2026-09-01-external-review-retry-degradation): a provider
returning HTTP 200 with a blank ``message.content`` is not an HTTP transport
error, so it was never retried even though ``llm_client.max_retries`` existed
in shared/config/external_review.json — the value was loaded but never read
by ``review_with_openrouter``/``review_with_openai``, so it was decorative.
This let a single transient empty reply become the permanent, final result
for an entire reviewer arm (observed: DeepSeek silently degraded across every
sampled iterate run from 2026-08-13 to 2026-08-31 while GPT carried the
cascade alone).

Fix: retry the completion call while ``classify_reply`` keeps returning
``degraded``, budgeted by the same ``llm_client.max_retries`` that is now
also passed to the ``OpenAI()`` client constructor (making the SDK's own
transport-level retry for 429/500/503 real instead of decorative). One
configured value governs both layers deliberately — a second, hardcoded
budget for "how hard do we try" would reintroduce a version of the same bug
this fix removes, just differently shaped. Worst-case combined network calls
is bounded at ``(max_retries+1)**2``, rarely reached in practice: a
persistent transport fault almost always ends by the SDK *raising* once its
own budget is exhausted (not retried at this layer — see
``retrying_completion``'s docstring) rather than by returning HTTP 200 with
degraded content on every attempt. The guaranteed win of the app-level retry
is recovering a genuinely transient hiccup; a systematic failure (e.g. a
reasoning model exhausting its token budget before emitting visible content)
repeats identically regardless of attempt count, where the loud
partial-degradation signal + auto-filed triage card carries the rest.
"""

import copy
import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
for _p in (_SHARED / "scripts" / "tools", _SHARED / "scripts" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from external_review_config import load_review_config  # noqa: E402


def _config(**llm_client_overrides):
    """The real shipping config (routing/model bindings must validate) with
    just `llm_client` overridden — hand-rolling a minimal dict would skip
    past `deepseek_routing`/model-identity validation instead of exercising it."""
    config = copy.deepcopy(load_review_config())
    config["llm_client"].update(llm_client_overrides)
    return config


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content, finish_reason="stop"):
        self.message = _FakeMessage(content)
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [_FakeChoice(content, finish_reason)]


def _make_fake_openai(responses, captured_ctor_kwargs):
    """Fake ``openai.OpenAI`` whose ``create()`` returns one of ``responses``
    per call (last one repeats once exhausted) and records constructor kwargs."""

    calls = {"count": 0}

    class _FakeCompletions:
        def create(self, **_kwargs):
            i = min(calls["count"], len(responses) - 1)
            calls["count"] += 1
            return responses[i]

    class _FakeChatNS:
        completions = _FakeCompletions()

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured_ctor_kwargs.update(kwargs)
            self.chat = _FakeChatNS()

    return _FakeOpenAI, calls


def test_empty_reply_is_retried_and_a_later_success_wins(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review
    import openai

    ctor_kwargs: dict = {}
    fake_cls, calls = _make_fake_openai(
        [_FakeResponse(""), _FakeResponse("a real review")], ctor_kwargs
    )
    monkeypatch.setattr(openai, "OpenAI", fake_cls)

    config = _config(max_retries=3)
    result = external_review.review_with_openrouter(
        "PLAN", "SPEC", "system", "user {SPEC} {PLAN}", config, "deepseek",
    )

    assert result["status"] == "success"
    assert result["feedback"] == "a real review"
    assert calls["count"] == 2  # first empty, second succeeded — stopped retrying


def test_retries_exhaust_and_report_degraded(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review
    import openai

    ctor_kwargs: dict = {}
    fake_cls, calls = _make_fake_openai([_FakeResponse("")], ctor_kwargs)
    monkeypatch.setattr(openai, "OpenAI", fake_cls)

    config = _config(max_retries=2)
    result = external_review.review_with_openrouter(
        "PLAN", "SPEC", "system", "user {SPEC} {PLAN}", config, "deepseek",
    )

    assert result["status"] == "degraded"
    assert calls["count"] == 2 + 1  # max_retries + 1 total attempts


def test_degraded_reply_retry_count_is_budgeted_by_llm_client_max_retries(monkeypatch):
    """AC1: the app-level degraded-reply retry count is controlled by the
    shipped `llm_client.max_retries` config value, not a hardcoded constant —
    changing the config must change the number of attempts."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review
    import openai

    ctor_kwargs: dict = {}
    fake_cls, calls = _make_fake_openai([_FakeResponse("")], ctor_kwargs)
    monkeypatch.setattr(openai, "OpenAI", fake_cls)

    config = _config(max_retries=4)
    external_review.review_with_openrouter(
        "PLAN", "SPEC", "system", "user {SPEC} {PLAN}", config, "deepseek",
    )

    assert calls["count"] == 4 + 1


def test_max_retries_is_wired_into_the_openrouter_client_constructor(monkeypatch):
    """The dead config: `llm_client.max_retries` must now reach OpenAI()'s own
    constructor so the SDK's transport-level retry (429/500/503) is real."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review
    import openai

    ctor_kwargs: dict = {}
    fake_cls, _calls = _make_fake_openai([_FakeResponse("ok")], ctor_kwargs)
    monkeypatch.setattr(openai, "OpenAI", fake_cls)

    config = _config(max_retries=5)
    external_review.review_with_openrouter(
        "PLAN", "SPEC", "system", "user {SPEC} {PLAN}", config, "deepseek",
    )

    assert ctor_kwargs.get("max_retries") == 5


def test_negative_max_retries_is_clamped_to_zero(monkeypatch):
    """A hand-edited negative `max_retries` must not reach OpenAI()'s
    constructor negative — doubt-review flagged this as producing a
    misleading zero-attempt 'provider returned nothing' result."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review
    import openai

    ctor_kwargs: dict = {}
    fake_cls, _calls = _make_fake_openai([_FakeResponse("ok")], ctor_kwargs)
    monkeypatch.setattr(openai, "OpenAI", fake_cls)

    config = _config(max_retries=-1)
    external_review.review_with_openrouter(
        "PLAN", "SPEC", "system", "user {SPEC} {PLAN}", config, "deepseek",
    )

    assert ctor_kwargs.get("max_retries") == 0


def test_max_retries_defaults_when_config_omits_it(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review
    import openai

    ctor_kwargs: dict = {}
    fake_cls, _calls = _make_fake_openai([_FakeResponse("ok")], ctor_kwargs)
    monkeypatch.setattr(openai, "OpenAI", fake_cls)

    config = copy.deepcopy(load_review_config())
    config["llm_client"].pop("max_retries", None)
    external_review.review_with_openrouter(
        "PLAN", "SPEC", "system", "user {SPEC} {PLAN}", config, "deepseek",
    )

    from external_review_degraded import DEFAULT_MAX_RETRIES
    assert ctor_kwargs.get("max_retries") == DEFAULT_MAX_RETRIES


def test_review_with_openai_also_retries_an_empty_reply(monkeypatch):
    """The direct-OpenAI path shares the same call shape and the same gap."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    import external_review
    import openai

    ctor_kwargs: dict = {}
    fake_cls, calls = _make_fake_openai(
        [_FakeResponse(""), _FakeResponse("a real review")], ctor_kwargs
    )
    monkeypatch.setattr(openai, "OpenAI", fake_cls)

    config = _config(max_retries=3)
    result = external_review.review_with_openai(
        "PLAN", "SPEC", "system", "user {SPEC} {PLAN}", config,
    )

    assert result["status"] == "success"
    assert calls["count"] == 2
    assert ctor_kwargs.get("max_retries") == 3


def test_a_finish_reason_degradation_is_also_retried(monkeypatch):
    """Not just empty replies — a cut-off/truncated reply is equally
    non-retryable by HTTP status, so it must go through the same loop."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review
    import openai

    ctor_kwargs: dict = {}
    fake_cls, calls = _make_fake_openai(
        [_FakeResponse("cut off", finish_reason="length"),
         _FakeResponse("a complete review", finish_reason="stop")],
        ctor_kwargs,
    )
    monkeypatch.setattr(openai, "OpenAI", fake_cls)

    config = _config(max_retries=3)
    result = external_review.review_with_openrouter(
        "PLAN", "SPEC", "system", "user {SPEC} {PLAN}", config, "deepseek",
    )

    assert result["status"] == "success"
    assert calls["count"] == 2

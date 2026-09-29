"""``llm_review.run_review(driver=...)`` — the {glm, opus} roster under codex.

Mirrors ``external_review.py --driver`` for the second, separate review copy
(used by adopt's Layer-3 review): a Codex-driven run swaps the OpenAI-family
'openai' leg for the cross-vendor 'opus' leg, and the default ``claude`` driver
keeps today's {glm, openai} roster unchanged.
"""

import sys
from pathlib import Path

import pytest

_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import llm_review  # noqa: E402
from external_review_modes import render_user_prompt_as_stdin_refs  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


def _tripwire(message):
    def _raise(*_a, **_k):
        raise AssertionError(message)
    return _raise


def _ok(via):
    return {"status": "success", "feedback": f"review via {via}", "via": via}


def _stub_opus_route(monkeypatch, route, note=""):
    monkeypatch.setattr(llm_review, "resolve_opus_route", lambda *_a, **_k: (route, note))


def test_codex_driver_roster_is_glm_and_opus_via_claude_cli(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")  # must NOT revive an 'openai' leg
    _stub_opus_route(monkeypatch, "claude_cli")
    monkeypatch.setattr(llm_review, "_review_openrouter", lambda *a: _ok("openrouter"))
    cli_args = []

    def _cli_leg(*args):
        cli_args.extend(args)
        return _ok("claude_cli")

    monkeypatch.setattr(llm_review, "_review_claude_cli", _cli_leg)
    monkeypatch.setattr(
        llm_review, "resolve_openai_route",
        _tripwire("resolve_openai_route must not run under driver=codex"),
    )

    result = llm_review.run_review("the-content", "the-context", driver="codex")

    content, context, _system, user_prompt, _config = cli_args
    assert (content, context) == ("the-content", "the-context")
    rendered = render_user_prompt_as_stdin_refs(user_prompt)
    assert "{CONTENT}" not in user_prompt and "{CONTEXT}" not in user_prompt
    assert "{" not in rendered  # no unfilled placeholder reaches the CLI instructions

    assert set(result["reviews"]) == {"glm", "opus"}
    assert result["reviews"]["opus"]["via"] == "claude_cli"
    assert result["provider"] == "claude_cli"
    assert result["success"] is True and result["partial"] is False


def test_codex_driver_opus_falls_back_to_openrouter_with_opus_identity(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    _stub_opus_route(monkeypatch, "openrouter", "claude CLI unavailable; falling back to openrouter")
    seen = []

    def _leg(content, context, system_prompt, user_prompt, config, model_key, timeout):
        seen.append(model_key)
        return _ok("openrouter")

    monkeypatch.setattr(llm_review, "_review_openrouter", _leg)

    result = llm_review.run_review("content", "context", driver="codex")

    assert sorted(seen) == ["glm", "opus"]
    assert "claude CLI unavailable" in result["reviews"]["opus"]["fallback_reason"]
    assert result["provider"] == "openrouter"


def test_codex_driver_without_any_route_skips_opus_and_is_unsuccessful(monkeypatch):
    _stub_opus_route(monkeypatch, "none")

    result = llm_review.run_review("content", "context", driver="codex")

    assert result["reviews"]["opus"]["status"] == "skipped"
    assert "openai" not in result["reviews"]
    assert result["success"] is False


def test_default_driver_keeps_the_openai_roster(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setattr(llm_review, "_review_openai", lambda *_a: _ok("direct"))
    monkeypatch.setattr(
        llm_review, "resolve_opus_route",
        _tripwire("resolve_opus_route must not run under driver=claude"),
    )

    result = llm_review.run_review("content", "context")

    assert set(result["reviews"]) == {"glm", "openai"}
    assert result["provider"] == "direct"


def test_unknown_driver_is_rejected_before_any_leg_runs():
    with pytest.raises(ValueError, match="unknown driver"):
        llm_review.run_review("content", "context", driver="gemini")


def test_gateway_route_is_unaffected_by_driver(monkeypatch):
    monkeypatch.setattr(llm_review, "gateway_configured", lambda: True)
    monkeypatch.setattr(llm_review, "_review_gateway", lambda *a: _ok("gateway"))

    result = llm_review.run_review("content", "context", driver="codex")

    assert set(result["reviews"]) == {"model-1", "model-2"}
    assert result["provider"] == "gateway"

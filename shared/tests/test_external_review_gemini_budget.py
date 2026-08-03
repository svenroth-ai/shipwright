"""Direct-Gemini reasoning budget, and llm_review's dual-import contract
(iterate-2026-08-01-llm-review-truncation-guard).

Sibling of ``test_external_review_budget.py`` (measured budget table +
OpenRouter/OpenAI parity pins) and of ``test_llm_review_import_modes.py``
(the dual-import contract).

**Why the direct-Gemini arm alone carries a fallback.** Both external plan
reviewers flagged that sending a reasoning parameter unconditionally could be
rejected by a model reached through a ``SHIPWRIGHT_REVIEW_MODEL_*`` override.
Measured for OpenRouter: ``openai/gpt-4o-mini`` — a non-reasoning model —
accepted ``extra_body={"reasoning": …}`` without error, because OpenRouter
normalises the field. The direct-Gemini arm is unmeasurable in this
environment (no direct key), so it retries once without ``thinking_config``
rather than matching on model names, which would rot as model names change.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
for _p in (_SHARED / "scripts" / "lib", _SHARED / "scripts" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from external_review_degraded import DEFAULT_TIMEOUT_SECONDS, MAX_OUTPUT_TOKENS, REASONING_MAX_TOKENS  # noqa: E402


def _fake_genai(
    captured: dict, *, text="REVIEW", finish_reason="STOP", fail_first=False,
    enum_style="named",
):
    """Stands in for ``google.genai``, capturing each GenerateContentConfig.

    ``fail_first`` simulates a model that rejects ``thinking_config`` with a
    400, so the retry path can be driven without a live key.

    ``enum_style`` selects which of google-genai's two observed renderings the
    fake finish reason uses, because they take different branches in
    ``gemini_finish_reason`` / ``_normalize_finish_reason``:

    * ``named``  — exposes ``.name``, so the bare name is returned directly.
    * ``dotted`` — no ``.name``, so ``str()`` yields ``FinishReason.MAX_TOKENS``
      and the normalizer's ``rsplit(".")`` branch is what has to strip it.

    Testing only ``named`` would leave the dotted branch unexercised while
    appearing to cover it (spec-reviewer finding 5).
    """

    class _ThinkingConfig:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _Config:
        def __init__(self, **kw):
            self.__dict__.setdefault("thinking_config", None)
            self.__dict__.update(kw)

    class _Types:
        GenerateContentConfig = _Config
        ThinkingConfig = _ThinkingConfig

    class _NamedEnum:
        def __init__(self, name):
            self.name = name

        def __str__(self):
            return f"FinishReason.{self.name}"

    class _DottedEnum:
        """No ``.name`` — only the dotted ``str()`` rendering."""

        def __init__(self, name):
            self._n = name

        def __str__(self):
            return f"FinishReason.{self._n}"

    class _Cand:
        def __init__(self):
            enum = _NamedEnum if enum_style == "named" else _DottedEnum
            self.finish_reason = enum(finish_reason)

    class _Resp:
        def __init__(self):
            self.text = text
            self.candidates = [_Cand()]
    class _ParameterRejected(RuntimeError):
        status_code = 400

    class _Models:
        def __init__(self):
            self._calls = 0

        def generate_content(self, **kwargs):
            self._calls += 1
            captured.setdefault("calls", []).append(kwargs)
            if fail_first and self._calls == 1:
                raise _ParameterRejected("unknown parameter: thinking_config")
            return _Resp()

    class _Client:
        def __init__(self, **kw):
            captured["client_kwargs"] = kw
            self.models = _Models()

    return type("genai", (), {"Client": _Client, "types": _Types})


def _both_gemini_arms():
    """(module, callable) for each implementation's direct-Gemini arm."""
    import external_review
    import llm_review

    return (
        (llm_review, lambda: llm_review._review_gemini(
            "C", "X", "sys", "u", {"gemini": "gemini-3.1-pro-preview"}, 5)),
        (external_review, lambda: external_review.review_with_gemini(
            "P", "S", "sys", "u",
            {"models": {"gemini": "gemini-3.1-pro-preview"}})),
    )


# --- AC-5 --------------------------------------------------------------------

def test_direct_gemini_arms_send_thinking_budget(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    for module, call in _both_gemini_arms():
        captured: dict = {}
        monkeypatch.setattr(module, "_import_genai", lambda c=captured: _fake_genai(c))
        result = call()

        cfg = captured["calls"][0]["config"]
        assert cfg.max_output_tokens == MAX_OUTPUT_TOKENS
        assert cfg.thinking_config.thinking_budget == REASONING_MAX_TOKENS
        assert result["status"] == "success"


@pytest.mark.parametrize("enum_style", ["named", "dotted"])
def test_direct_gemini_degrades_a_truncated_reply(monkeypatch, enum_style):
    """Both google-genai finish-reason renderings must degrade.

    ``dotted`` is the case that actually exercises the normalizer's
    ``rsplit(".")`` branch; ``named`` short-circuits on ``.name``.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    for module, call in _both_gemini_arms():
        captured: dict = {}
        monkeypatch.setattr(
            module, "_import_genai",
            lambda c=captured: _fake_genai(
                c, text="1. Findi", finish_reason="MAX_TOKENS", enum_style=enum_style
            ),
        )
        assert call()["status"] == "degraded"


def test_direct_gemini_client_carries_a_bounded_timeout(monkeypatch):
    """Both direct-Gemini clients must bound the call — in MILLISECONDS.

    Previously neither path passed a timeout at all, so a hung call was
    unbounded; that matters more now, because ``gemini_generate`` can issue a
    second call. google-genai's ``http_options.timeout`` is milliseconds while
    every other timeout in this repo is seconds, so the conversion is exactly
    the kind of thing that rots silently — and the fake used to swallow every
    client kwarg, leaving this the one change with no coverage at all
    (doubt review, doubt 4).
    """
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    # llm_review's arm is driven with 5 seconds; external_review receives no
    # timeout key and must use the same shared default as llm_review's public
    # default. Both must convert seconds to milliseconds.
    for module, call in _both_gemini_arms():
        captured: dict = {}
        monkeypatch.setattr(module, "_import_genai", lambda c=captured: _fake_genai(c))
        call()

        http_options = captured["client_kwargs"]["http_options"]
        expected = 5000 if module.__name__ == "llm_review" else DEFAULT_TIMEOUT_SECONDS * 1000
        assert http_options["timeout"] == expected, (
            f"{module.__name__} passed {http_options['timeout']} — expected "
            f"{expected} ms"
        )


# --- AC-10 -------------------------------------------------------------------

def test_direct_gemini_retries_without_reasoning_when_model_rejects_it(monkeypatch):
    """An overridden model that rejects thinking_config must not turn a working
    review into an error."""
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    for module, call in _both_gemini_arms():
        captured: dict = {}
        monkeypatch.setattr(
            module, "_import_genai", lambda c=captured: _fake_genai(c, fail_first=True)
        )
        result = call()

        assert len(captured["calls"]) == 2, "should retry exactly once"
        assert captured["calls"][0]["config"].thinking_config is not None
        assert captured["calls"][1]["config"].thinking_config is None
        # Budget is retained on the retry — only the reasoning knob is dropped.
        assert captured["calls"][1]["config"].max_output_tokens == MAX_OUTPUT_TOKENS
        assert result["status"] == "success"
        # The fallback must survive into the machine-readable reply, not only
        # onto stderr — no consumer captures stderr.
        assert "UNBOUNDED" in result["reasoning_cap_dropped"]


def test_an_old_sdk_without_thinking_config_still_reviews(monkeypatch):
    """`_config(True)` is built INSIDE the try on purpose.

    A google-genai too old to expose `types.ThinkingConfig` raises
    AttributeError while the config is being constructed, and must take the
    same fallback. Hoisting that construction above the `try` would turn an
    old-SDK environment from "review works" into "status: error" with every
    other test still green — so pin it.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def _genai_without_thinking_config(captured):
        fake = _fake_genai(captured)
        del fake.types.ThinkingConfig
        return fake

    for module, call in _both_gemini_arms():
        captured: dict = {}
        monkeypatch.setattr(
            module, "_import_genai", lambda c=captured: _genai_without_thinking_config(c)
        )
        result = call()

        assert result["status"] == "success"
        assert len(captured["calls"]) == 1, "the failed attempt never reached the client"
        assert captured["calls"][0]["config"].max_output_tokens == MAX_OUTPUT_TOKENS


def test_real_sdk_accepts_the_config_shape_we_send():
    """Catches an SDK field RENAME, which the permissive fake cannot.

    The fakes above accept any kwarg, so `thinking_budget` -> some new name
    would pass them silently. This builds the real pydantic models instead.

    SKIPS in the shared-root CI run: google-genai is a shipwright-plan
    dependency, not a root one. A skip here is therefore NOT coverage of this
    arm — it is stated so the skip is never mistaken for one.
    """
    genai_types = pytest.importorskip(
        "google.genai.types", reason="google-genai not installed in this root"
    )
    thinking = genai_types.ThinkingConfig(thinking_budget=REASONING_MAX_TOKENS)
    cfg = genai_types.GenerateContentConfig(
        system_instruction="x",
        max_output_tokens=MAX_OUTPUT_TOKENS,
        thinking_config=thinking,
    )
    assert cfg.max_output_tokens == MAX_OUTPUT_TOKENS
    assert cfg.thinking_config.thinking_budget == REASONING_MAX_TOKENS


def test_missing_google_genai_is_reported_not_swallowed(monkeypatch):
    """The `_import_genai` seam is a real lazy import, not a stub.

    `google-genai` is deliberately NOT a project dependency (only `openai` is),
    so the direct-Gemini arm must degrade to a named error rather than raising
    out of the arm. This exercises the seam's real body — the one line the
    monkeypatched tests above necessarily skip — and pins the message a user
    actually sees when the optional dependency is absent.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    try:
        from google import genai  # noqa: F401
    except ImportError:
        pass
    else:
        # Not a silent skip: if the optional dep ever becomes a real
        # dependency, this path stops existing and the test should say so
        # rather than quietly passing.
        pytest.skip("google-genai is installed — the missing-dependency path cannot occur")

    # Called WITHOUT patching `_import_genai`, so the real seam runs.
    for _module, call in _both_gemini_arms():
        got = call()
        assert got["status"] == "error"
        assert "google-genai" in got["reason"]

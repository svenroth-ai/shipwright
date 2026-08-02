"""The reply budget, and the two review paths that must not drift apart
(iterate-2026-08-01-llm-review-truncation-guard).

Measured on a 209,549-char review prompt against
``google/gemini-3.1-pro-preview``:

===========  =============  ================  ==============  ===============
max_tokens   reasoning cap  reasoning_tokens  visible chars   finish_reason
===========  =============  ================  ==============  ===============
4096         none           3928 / 4092       621             length
16000        none           15360 / 15996     2352            length
16000        2000           3332              13448           stop
16000        2000           3791              14134           stop
16000        2000           6909              14077           stop
===========  =============  ================  ==============  ===============

Two things that table supports — stated as what was measured, not as a law:

1. **Raising the total budget alone did not fix it.** On both uncapped runs
   reasoning consumed essentially the whole ceiling and the answer was cut off,
   at 4096 and at 16000 alike. (Whether the burn *scales* with the ceiling or
   simply exceeds every ceiling tried is not distinguished by these points —
   either way the cap is doing real work, and an edit that drops it while
   keeping a large ``max_tokens`` restores the bug.)
2. **The cap is weak, not exact.** The same cap of 2000 produced 3332, 3791 and
   6909 across three runs — up to a 3.5x overshoot with 2x run-to-run variance.
   So the total must absorb a *multiple* of the cap plus a full answer, which is
   why the invariant below is absolute rather than a ratio.

The two paths — ``lib/llm_review.py`` and ``tools/external_review.py`` — are
independent implementations of the same review call. They already drifted once
(the truncation classifier landed in one and not the other, which is the
fail-open this run fixes), so parity is pinned behaviorally: same budget, same
cap, same degradation verdict, asserted from captured client kwargs rather than
by scanning source.

Direct-Gemini reasoning budget and the dual-import contract live in the sibling
``test_external_review_gemini_budget.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
for _p in (_SHARED / "scripts" / "lib", _SHARED / "scripts" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from external_review_degraded import (  # noqa: E402
    DEFAULT_TIMEOUT_SECONDS,
    MAX_OUTPUT_TOKENS,
    REASONING_MAX_TOKENS,
    openrouter_extra_body,
)

_EXT_CONFIG = {
    "models": {"openrouter_gemini": "g", "chatgpt": "gpt-5.6-terra"},
    "llm_client": {"timeout_seconds": 5},
}


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content, finish_reason):
        self.message = _Msg(content)
        self.finish_reason = finish_reason


class _OpenAIResponse:
    def __init__(self, content, finish_reason):
        self.choices = [_Choice(content, finish_reason)]


def _fake_openai(captured: dict, content="REVIEW_BODY", finish_reason="stop"):
    """Fake ``openai.OpenAI`` recording the create() kwargs (repo idiom)."""

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _OpenAIResponse(content, finish_reason)

    class _ChatNS:
        completions = _Completions()

    class _Client:
        def __init__(self, **kw):
            captured["client_kwargs"] = kw
            self.chat = _ChatNS()

    return _Client


def _call_both_openrouter(monkeypatch, content, finish_reason):
    """Drive the OpenRouter arm of both modules; return (llm, ext) results."""
    import openai

    import external_review
    import llm_review

    cap_llm: dict = {}
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(cap_llm, content, finish_reason))
    got_llm = llm_review._review_openrouter(
        "C", "X", "sys", "u {CONTENT} {CONTEXT}", llm_review.DEFAULT_MODELS, "gemini", 5
    )

    cap_ext: dict = {}
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(cap_ext, content, finish_reason))
    got_ext = external_review.review_with_openrouter(
        "P", "S", "sys", "u {PLAN} {SPEC}", _EXT_CONFIG, "gemini"
    )
    return (got_llm, cap_llm), (got_ext, cap_ext)


# --- the constants themselves ------------------------------------------------

#: Worst measured overshoot of the reasoning cap (2000 requested -> 6909 actual).
_MAX_OBSERVED_CAP_OVERSHOOT = 3.5
#: Tokens a complete review actually needs (~14000 visible chars).
_ANSWER_TOKENS = 3500


def test_budget_leaves_room_for_an_overshot_cap_plus_a_full_answer():
    """The coupling is ABSOLUTE, not a ratio — and that distinction is the test.

    A ratio invariant (`total >= cap * 4`) is scale-invariant, but the failure
    is not: `(4096, 1024)` satisfies it and reproduces the original bug exactly
    — at the measured overshoot that cap yields ~3600 reasoning tokens, leaving
    ~500 for an answer that needs ~3500. The doubt review constructed those
    values against the earlier ratio assertion, so this pins the mechanism
    instead: whatever the pair, the total must absorb a 3.5x-overshot cap AND
    still fit a complete review.

    Shrinking the total is the likelier future edit (it is the one that saves
    money), and a ratio guards that direction not at all.
    """
    assert REASONING_MAX_TOKENS < MAX_OUTPUT_TOKENS

    worst_case_reasoning = REASONING_MAX_TOKENS * _MAX_OBSERVED_CAP_OVERSHOOT
    assert MAX_OUTPUT_TOKENS - worst_case_reasoning >= _ANSWER_TOKENS, (
        f"{MAX_OUTPUT_TOKENS} total - {worst_case_reasoning:.0f} worst-case "
        f"reasoning leaves less than the {_ANSWER_TOKENS} tokens a complete "
        "review needs; this is the original truncation bug"
    )


def test_the_invariant_rejects_the_values_that_reproduce_the_bug():
    """Meta-test: prove the assertion above actually discriminates.

    `(4096, 1024)` passed the ratio invariant it replaced. If a future
    refactor weakens the check back into a ratio, this fails.
    """
    def _fits(total: int, cap: int) -> bool:
        return total - cap * _MAX_OBSERVED_CAP_OVERSHOOT >= _ANSWER_TOKENS

    assert _fits(MAX_OUTPUT_TOKENS, REASONING_MAX_TOKENS), "shipped pair must pass"
    assert _fits(16000, 3000), "a modest cap raise still fits under the same total"
    assert not _fits(4096, 1024), "the ratio-satisfying bug case must be rejected"
    assert not _fits(400, 100), "and so must its scaled-down twin"
    # Binds in the raise-the-cap direction too. This one is easy to get wrong by
    # eye: 16000 - 4000*3.5 = 2000, which is BELOW the answer budget — so a cap
    # of 4000 needs a bigger total, not the same one. Asserted because the
    # constant block originally claimed 4000 was safe at 16000, and it is not.
    assert not _fits(16000, 4000), "cap 4000 does NOT fit under a 16000 total"
    assert _fits(20000, 4000), "cap 4000 needs the total raised to ~20000"


def test_extra_body_caps_only_the_arm_that_needed_it():
    """The cap ships ONLY on gemini.

    gpt-5.6-terra never truncated at 4096, and the measurement that showed
    the cap non-binding there used a prompt where GPT reasoned 1220 < 2000 —
    which says nothing about a prompt where it wants more. Sending an
    unmeasurable knob to the highest-yield review pass for no demonstrated
    benefit is the risk this scoping removes (doubt review, C3).
    """
    assert openrouter_extra_body("gemini") == {"reasoning": {"max_tokens": REASONING_MAX_TOKENS}}
    assert openrouter_extra_body("openai") == {}


# --- AC-3 / AC-4 / AC-7: parity across the two paths -------------------------

def test_openrouter_arms_agree_on_budget_and_cap(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    (_, cap_llm), (_, cap_ext) = _call_both_openrouter(monkeypatch, "REVIEW_BODY", "stop")

    assert cap_llm["max_tokens"] == MAX_OUTPUT_TOKENS
    assert cap_ext["max_tokens"] == cap_llm["max_tokens"]

    # Both arms driven with model_key="gemini", so both carry the cap — and
    # carry the SAME one. Scoping is pinned separately above.
    expected = {"reasoning": {"max_tokens": REASONING_MAX_TOKENS}}
    assert cap_llm["extra_body"] == expected
    assert cap_ext["extra_body"] == expected


def test_direct_openai_arms_agree_on_budget(monkeypatch):
    """gpt-5.x needs max_completion_tokens; both paths must send the same one."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    import openai

    import external_review
    import llm_review

    cap_llm: dict = {}
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(cap_llm))
    llm_review._review_openai("C", "X", "sys", "u", {"chatgpt": "gpt-5.6-terra"}, 5)

    cap_ext: dict = {}
    monkeypatch.setattr(openai, "OpenAI", _fake_openai(cap_ext))
    external_review.review_with_openai("P", "S", "sys", "u", _EXT_CONFIG)

    for cap in (cap_llm, cap_ext):
        assert "max_tokens" not in cap
        assert cap["max_completion_tokens"] == MAX_OUTPUT_TOKENS


def test_external_review_openai_clients_default_to_shared_timeout(monkeypatch):
    """Missing config must not revive the old 120-second timeout."""
    import openai

    import external_review

    calls = (
        (
            "OPENROUTER_API_KEY",
            lambda config: external_review.review_with_openrouter(
                "P", "S", "sys", "u", config, "gemini"
            ),
            {"models": {"openrouter_gemini": "g"}},
        ),
        (
            "OPENAI_API_KEY",
            lambda config: external_review.review_with_openai(
                "P", "S", "sys", "u", config
            ),
            {"models": {"chatgpt": "gpt-5.6-terra"}},
        ),
    )
    for env_key, call, config in calls:
        monkeypatch.setenv(env_key, "test-key")
        captured: dict = {}
        monkeypatch.setattr(openai, "OpenAI", _fake_openai(captured))

        assert call(config)["status"] == "success"
        assert captured["client_kwargs"]["timeout"] == DEFAULT_TIMEOUT_SECONDS
        monkeypatch.delenv(env_key)


# --- AC-1 / AC-2 / AC-7: both paths degrade a non-review ---------------------

def test_both_paths_degrade_a_truncated_reply(monkeypatch):
    """The fail-open this run fixes: a cut-off reply is not a success."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    (got_llm, _), (got_ext, _) = _call_both_openrouter(monkeypatch, "1. Findi", "length")

    assert got_llm["status"] == "degraded"
    assert got_ext["status"] == "degraded"
    # The partial text survives so a human can still read what arrived.
    assert got_llm["feedback"] == "1. Findi"
    assert "cut off" in got_llm["reason"]


def test_both_paths_degrade_an_empty_reply(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    (got_llm, _), (got_ext, _) = _call_both_openrouter(monkeypatch, "", "stop")

    assert got_llm["status"] == "degraded"
    assert got_ext["status"] == "degraded"


def test_a_complete_reply_is_still_a_success(monkeypatch):
    """Guard against over-correction: the fix must not reject real reviews."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    (got_llm, _), (got_ext, _) = _call_both_openrouter(
        monkeypatch, "1. **Finding:** real", "stop"
    )
    assert got_llm["status"] == "success"
    assert got_ext["status"] == "success"


def test_run_review_success_is_false_when_every_leg_is_degraded(monkeypatch):
    """AC-1's aggregate half: half a review must not green the gate."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import openai

    import llm_review

    monkeypatch.setattr(
        openai, "OpenAI", _fake_openai({}, content="cut off", finish_reason="length")
    )
    result = llm_review.run_review("content", "context")

    assert result["success"] is False
    assert {r["status"] for r in result["reviews"].values()} == {"degraded"}

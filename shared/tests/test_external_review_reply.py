"""A reply that is not a review is not a success
(iterate-2026-07-27-name-the-blocker).

Observed on iterate-2026-07-27-f0-race-triage: the Gemini leg returned an
unfinished internal monologue while the transport reported success, so the leg
was recorded `status: "success"` and only a human reading the text downstream
noticed nothing had been reviewed. Same class as the rest of this change —
success reported, nothing delivered.

**Only signals the provider itself gives.** An empty answer, truncation, or a
known abnormal terminal reason such as `content_filter` / Gemini `SAFETY`.
Deliberately no prose heuristics: a classifier guessing whether text "reads like
a review" would eventually reject a real one, and a review gate that rejects real
reviews is worse than one that occasionally lets a bad one through — the
downstream reader still sees the text.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.external_review_degraded import (  # noqa: E402
    classify_reply,
    finalize_review_output,
    gemini_finish_reason,
    openai_finish_reason,
)


class _Enum:
    """Stands in for google-genai's FinishReason enum (`str()` renders dotted)."""

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"FinishReason.{self.name}"


class _OpenAI:
    def __init__(self, finish_reason):
        self.choices = [type("C", (), {"finish_reason": finish_reason})()]


class _Gemini:
    def __init__(self, finish_reason):
        self.candidates = [type("C", (), {"finish_reason": finish_reason})()]


# --- what counts as a review --------------------------------------------------

def test_a_real_reply_is_a_success():
    out = classify_reply("1. **Finding:** something is wrong", "stop", via="openrouter")
    assert out["status"] == "success"
    assert out["feedback"].startswith("1.")
    assert out["via"] == "openrouter"


def test_an_empty_reply_is_degraded():
    out = classify_reply("", "stop", via="direct")
    assert out["status"] == "degraded"
    assert "empty" in out["reason"].lower()


def test_a_whitespace_only_reply_is_degraded():
    assert classify_reply("   \n\t ", "stop", via="direct")["status"] == "degraded"


def test_a_none_reply_is_degraded():
    assert classify_reply(None, "stop", via="direct")["status"] == "degraded"


def test_a_truncated_reply_is_degraded_even_though_text_arrived():
    """The observed failure: text came back, the transport was happy, and the
    model had been cut off mid-thought."""
    out = classify_reply("Let me think about this. First I should", "length", via="openrouter")
    assert out["status"] == "degraded"
    assert "cut off" in out["reason"].lower()
    assert out["feedback"]  # the partial text is still carried, for a human to read


def test_gemini_max_tokens_is_a_truncation():
    assert classify_reply("partial", "MAX_TOKENS", via="direct")["status"] == "degraded"


def test_a_missing_finish_reason_stays_neutral():
    """External review, GPT-11: absent metadata is not evidence of truncation.
    Degrading on it would fail every provider that omits the field."""
    assert classify_reply("a real review", None, via="direct")["status"] == "success"
    assert classify_reply("a real review", "", via="direct")["status"] == "success"


def test_known_abnormal_finish_reasons_are_degraded():
    reasons = (
        "content_filter", "MAX_TOKENS", "SAFETY", "RECITATION", "LANGUAGE",
        "OTHER", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII",
        "MALFORMED_FUNCTION_CALL", "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT",
        "NO_IMAGE", "IMAGE_RECITATION", "IMAGE_OTHER", "UNEXPECTED_TOOL_CALL",
        "TOO_MANY_TOOL_CALLS", "tool_calls", "function_call",
    )
    for reason in reasons:
        assert classify_reply("partial", reason, via="direct")["status"] == "degraded"


def test_an_unknown_finish_reason_stays_neutral():
    assert classify_reply("a real review", "future_reason", via="direct")["status"] == "success"


# --- reading finish_reason off each provider's response -----------------------

def test_openai_finish_reason_is_read_from_the_first_choice():
    assert openai_finish_reason(_OpenAI("length")) == "length"


def test_gemini_finish_reason_handles_the_enum_form():
    """google-genai gives an enum whose `str()` is `FinishReason.MAX_TOKENS`."""
    assert gemini_finish_reason(_Gemini(_Enum("MAX_TOKENS"))) == "MAX_TOKENS"


def test_gemini_finish_reason_handles_a_plain_string():
    assert gemini_finish_reason(_Gemini("STOP")) == "STOP"


def test_finish_reason_readers_never_raise_on_an_unexpected_shape():
    for reader in (openai_finish_reason, gemini_finish_reason):
        assert reader(object()) == ""
        assert reader(None) == ""


def test_empty_candidate_list_is_not_a_crash():
    empty = type("R", (), {"candidates": []})()
    assert gemini_finish_reason(empty) == ""


# --- how a degraded leg flows into the gate -----------------------------------

def test_one_degraded_leg_does_not_count_as_a_succeeded_review():
    reviews = {
        "gemini": classify_reply("cut off", "MAX_TOKENS", via="direct"),
        "openai": classify_reply("a real review", "stop", via="direct"),
    }
    output, code = finalize_review_output("direct", reviews)
    assert output["reviews_succeeded"] == 1     # not 2
    assert output["degraded"] is False          # one real review DID land
    assert code == 0
    assert output["reviews"]["gemini"]["status"] == "degraded"  # and it is visible


def test_every_leg_degraded_fails_the_gate_loudly():
    """The case the old code reported as a clean pass: both providers answered,
    neither delivered a review."""
    reviews = {
        "gemini": classify_reply("", "stop", via="direct"),
        "openai": classify_reply("also cut", "length", via="direct"),
    }
    output, code = finalize_review_output("direct", reviews)
    assert output["success"] is False
    assert output["degraded"] is True
    assert code == 1
    assert "cut off" in output["degraded_reason"]


def test_the_reason_survives_into_the_degraded_summary():
    reviews = {"gemini": classify_reply("", "stop", via="direct")}
    output, _ = finalize_review_output("direct", reviews)
    assert "empty" in output["degraded_reason"].lower()

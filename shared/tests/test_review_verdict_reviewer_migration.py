"""Current DeepSeek and historical Gemini verdict pairs. @FR-01.03 @FR-01.11"""

from lib.review_marker import STATE_OK, evaluate_review_state
from lib.review_verdict import contradiction_block, summarize_reviews


def _pair(first: str, first_verdict: str, openai_verdict: str) -> dict:
    return {
        first: {
            "status": "success",
            "feedback": f"SHIPWRIGHT_VERDICT: {first_verdict}",
        },
        "openai": {
            "status": "success",
            "feedback": f"SHIPWRIGHT_VERDICT: {openai_verdict}",
        },
    }


def test_new_deepseek_pair_uses_the_existing_contradiction_semantics():
    out = summarize_reviews(_pair("deepseek", "approve", "reject"))
    assert out["verdicts"] == {"deepseek": "approve", "openai": "reject"}
    assert out["contradiction"]["detected"] is True
    assert out["contradiction"]["requires_resolution"] is True


def test_historical_gemini_pair_remains_readable():
    out = summarize_reviews(_pair("gemini", "approve", "revise"))
    assert out["verdicts"] == {"gemini": "approve", "openai": "revise"}
    assert out["contradiction"]["detected"] is False
    assert out["contradiction"]["requires_resolution"] is False


def test_schema_2_historical_gemini_marker_remains_readable():
    state, reason = evaluate_review_state({
        "marker_schema": 2,
        "status": "completed",
        "verdicts": {"gemini": "approve", "openai": "revise"},
    })
    assert state == STATE_OK
    assert reason == "status=completed"


def test_mixed_three_arm_mapping_fails_closed_as_ambiguous():
    block = contradiction_block({
        "deepseek": "approve",
        "gemini": "approve",
        "openai": "approve",
    })
    assert block["requires_resolution"] is True
    assert "unexpected reviewer set" in block["reason"]


def test_mixed_generation_pair_is_not_reinterpreted():
    block = contradiction_block({"deepseek": "approve", "gemini": "approve"})
    assert block["requires_resolution"] is True
    assert "unexpected reviewer set" in block["reason"]


def test_one_current_arm_unavailable_requires_resolution():
    reviews = _pair("deepseek", "approve", "reject")
    reviews["deepseek"] = {"status": "error", "reason": "no approved endpoint"}
    block = summarize_reviews(reviews)["contradiction"]
    assert block["requires_resolution"] is True
    assert "only one reviewer answered" in block["reason"]

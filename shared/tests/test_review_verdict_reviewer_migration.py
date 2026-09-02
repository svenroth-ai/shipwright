"""Current GLM and historical DeepSeek/Gemini verdict pairs. @FR-01.03 @FR-01.11"""

from lib.review_marker import STATE_BLOCK, STATE_OK, evaluate_review_state
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


def test_new_glm_pair_uses_the_existing_contradiction_semantics():
    out = summarize_reviews(_pair("glm", "approve", "reject"))
    assert out["verdicts"] == {"glm": "approve", "openai": "reject"}
    assert out["contradiction"]["detected"] is True
    assert out["contradiction"]["requires_resolution"] is True


def test_historical_deepseek_pair_remains_readable():
    out = summarize_reviews(_pair("deepseek", "approve", "revise"))
    assert out["verdicts"] == {"deepseek": "approve", "openai": "revise"}
    assert out["contradiction"]["detected"] is False
    assert out["contradiction"]["requires_resolution"] is False


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


def test_schema_3_historical_deepseek_marker_remains_readable():
    state, reason = evaluate_review_state({
        "marker_schema": 3,
        "status": "completed",
        "verdicts": {"deepseek": "approve", "openai": "revise"},
    })
    assert state == STATE_OK
    assert reason == "status=completed"


def test_schema_4_current_glm_marker_is_accepted():
    state, reason = evaluate_review_state({
        "marker_schema": 4,
        "status": "completed",
        "verdicts": {"glm": "approve", "openai": "revise"},
    })
    assert state == STATE_OK
    assert reason == "status=completed"


def test_unknown_marker_schema_fails_closed():
    state, reason = evaluate_review_state({
        "marker_schema": 999,
        "status": "completed",
        "verdicts": {"glm": "approve", "openai": "approve"},
    })
    assert state == STATE_BLOCK
    assert "unknown review marker schema" in reason


def test_schema_2_rejects_the_current_glm_roster():
    state, reason = evaluate_review_state({
        "marker_schema": 2,
        "status": "completed",
        "verdicts": {"glm": "approve", "openai": "approve"},
    })
    assert state == STATE_BLOCK
    assert "historical gemini/openai" in reason


def test_schema_3_rejects_the_current_glm_roster():
    state, reason = evaluate_review_state({
        "marker_schema": 3,
        "status": "completed",
        "verdicts": {"glm": "approve", "openai": "approve"},
    })
    assert state == STATE_BLOCK
    assert "historical schema 3 deepseek/openai" in reason


def test_schema_4_rejects_the_historical_deepseek_roster():
    state, reason = evaluate_review_state({
        "marker_schema": 4,
        "status": "completed",
        "verdicts": {"deepseek": "approve", "openai": "approve"},
    })
    assert state == STATE_BLOCK
    assert "schema 4 glm/openai" in reason


def test_marker_without_schema_only_uses_the_historical_gemini_roster():
    state, reason = evaluate_review_state({
        "status": "completed",
        "verdicts": {"glm": "approve", "openai": "approve"},
    })
    assert state == STATE_BLOCK
    assert "historical gemini/openai" in reason


def test_mixed_three_arm_mapping_fails_closed_as_ambiguous():
    block = contradiction_block({
        "glm": "approve",
        "gemini": "approve",
        "openai": "approve",
    })
    assert block["requires_resolution"] is True
    assert "unexpected reviewer set" in block["reason"]


def test_mixed_generation_pair_is_not_reinterpreted():
    block = contradiction_block({"glm": "approve", "gemini": "approve"})
    assert block["requires_resolution"] is True
    assert "unexpected reviewer set" in block["reason"]


def test_one_current_arm_unavailable_requires_resolution():
    reviews = _pair("glm", "approve", "reject")
    reviews["glm"] = {"status": "error", "reason": "no approved endpoint"}
    block = summarize_reviews(reviews)["contradiction"]
    assert block["requires_resolution"] is True
    assert "only one reviewer answered" in block["reason"]

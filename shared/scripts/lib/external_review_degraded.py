"""Reply completeness and loud degradation for external review."""

from __future__ import annotations

import sys

REVIEW_ENVELOPE_SCHEMA = 2

_ATTEMPTED_PROVIDERS = ("openrouter", "direct")
_BANNER = (
    "error: external review gate DEGRADED — API keys are present but no review "
    "succeeded ({reason}). This is NOT a silent skip: the caller must treat it "
    "as 'external review did not run', not mark the gate completed."
)

_DEGRADED_FINISH_REASONS = frozenset({
    "length", "max_tokens", "maxtokens", "content_filter", "safety",
    "recitation", "language", "other", "blocklist", "prohibited_content",
    "spii", "malformed_function_call", "image_safety",
    "image_prohibited_content", "no_image", "image_recitation", "image_other",
    "unexpected_tool_call", "too_many_tool_calls", "tool_calls",
    "function_call",
})

# Both review clients share these constants. The shipping timeout is pinned
# against DEFAULT_TIMEOUT_SECONDS by test_llm_review.py.
MAX_OUTPUT_TOKENS = 16000
DEFAULT_TIMEOUT_SECONDS = 240


def _normalize_finish_reason(raw: object) -> str:
    """Lower-cased reason for plain strings and enum-style values."""
    if raw is None:
        return ""
    name = getattr(raw, "name", None)
    text = name if isinstance(name, str) else str(raw)
    return text.rsplit(".", 1)[-1].strip().lower()


def openai_finish_reason(response: object) -> str:
    """Return ``choices[0].finish_reason``, or an empty string."""
    try:
        return str(response.choices[0].finish_reason or "")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — unreadable metadata is neutral
        return ""


def classify_reply(text: str | None, finish_reason: object, *, via: str) -> dict:
    """Shape one provider leg as success or explicitly degraded."""
    base = {"feedback": text, "via": via}
    if not (text or "").strip():
        return {
            **base,
            "status": "degraded",
            "reason": "provider returned an empty reply",
        }
    if _normalize_finish_reason(finish_reason) in _DEGRADED_FINISH_REASONS:
        return {
            **base,
            "status": "degraded",
            "reason": (
                "provider reported the reply was cut off or otherwise incomplete "
                f"(finish_reason={finish_reason})"
            ),
        }
    return {**base, "status": "success"}


def count_succeeded(reviews: dict) -> int:
    return sum(1 for review in reviews.values() if review.get("status") == "success")


def is_degraded(provider: str, reviews: dict) -> bool:
    return provider in _ATTEMPTED_PROVIDERS and count_succeeded(reviews) == 0


def degraded_reason(provider: str, reviews: dict) -> str:
    parts = "; ".join(
        f"{name}: {review.get('reason', review.get('status', 'unknown'))}"
        for name, review in sorted(reviews.items())
    )
    return f"provider={provider} but 0/{len(reviews)} reviews succeeded ({parts})"


def finalize_review_output(provider: str, reviews: dict) -> tuple[dict, int]:
    """Build the stable CLI payload and fail loudly on total provider failure."""
    succeeded = count_succeeded(reviews)
    degraded = is_degraded(provider, reviews)
    output: dict = {
        # Version 1 was implicit and used the historical gemini/openai roster.
        # Version 2 makes the deepseek/openai breaking roster change explicit.
        "review_schema": REVIEW_ENVELOPE_SCHEMA,
        "success": not degraded,
        "provider": provider,
        "degraded": degraded,
        "reviews_succeeded": succeeded,
        "reviews": reviews,
    }
    if degraded:
        reason = degraded_reason(provider, reviews)
        output["degraded_reason"] = reason
        print(_BANNER.format(reason=reason), file=sys.stderr)
    return output, (1 if degraded else 0)

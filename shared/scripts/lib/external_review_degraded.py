"""Reply completeness and loud degradation for external review."""

from __future__ import annotations

import sys
from pathlib import Path

REVIEW_ENVELOPE_SCHEMA = 2

_ATTEMPTED_PROVIDERS = ("openrouter", "direct")
_NON_SUCCESS_ATTEMPTED_STATUSES = frozenset({"degraded", "error"})
_BANNER = (
    "error: external review gate DEGRADED — API keys are present but no review "
    "succeeded ({reason}). This is NOT a silent skip: the caller must treat it "
    "as 'external review did not run', not mark the gate completed."
)
_PARTIAL_BANNER = (
    "warning: external review PARTIALLY degraded — {legs} did not return a "
    "usable reply while at least one other reviewer succeeded. The gate still "
    "reports success (one opinion is enough to proceed), but {legs}'s review "
    "is MISSING from this pass, silently, unless this warning is read."
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


def partially_degraded_legs(reviews: dict) -> list[str]:
    """Names of reviewer legs that were attempted and failed (``degraded`` or
    ``error``) — sorted for deterministic output. Excludes ``skipped`` legs:
    an intentionally-not-attempted reviewer (e.g. GLM with no direct
    route) is not a failure."""
    return sorted(
        name for name, review in reviews.items()
        if review.get("status") in _NON_SUCCESS_ATTEMPTED_STATUSES
    )


def is_partially_degraded(provider: str, reviews: dict) -> bool:
    """True when SOME but not ALL attempted legs failed.

    ``is_degraded`` only fires when EVERY leg fails — a mixed result (one
    reviewer degraded, another succeeded) reports ``success=True`` with no
    signal that a reviewer's opinion is silently missing from the pass. This
    is the gap that let a reviewer arm fail unnoticed for weeks while its
    sibling quietly carried the whole cascade.
    """
    if provider not in _ATTEMPTED_PROVIDERS:
        return False
    return bool(partially_degraded_legs(reviews)) and count_succeeded(reviews) > 0


def degraded_reason(provider: str, reviews: dict) -> str:
    parts = "; ".join(
        f"{name}: {review.get('reason', review.get('status', 'unknown'))}"
        for name, review in sorted(reviews.items())
    )
    return f"provider={provider} but 0/{len(reviews)} reviews succeeded ({parts})"


#: Default retry budget when `llm_client.max_retries` is absent from config —
#: matches the OpenAI SDK's own constructor default.
DEFAULT_MAX_RETRIES = 2

def llm_client_settings(config: dict) -> tuple[float, int]:
    """`(timeout_seconds, max_retries)` from `config["llm_client"]`, defaulted.

    `max_retries` also governs the OpenAI SDK's own transport-level retry
    (429/500/503) once passed to its client constructor — previously loaded
    from config but never passed anywhere, so it was decorative. Clamped to
    >= 0: a hand-edited negative value would otherwise reach the SDK/loop as
    `range(negative)` — zero attempts — and read as "provider returned
    nothing" with no hint the real cause was a misconfigured retry count.
    """
    llm_client = config.get("llm_client", {})
    max_retries = llm_client.get("max_retries", DEFAULT_MAX_RETRIES)
    return (
        llm_client.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        max(0, max_retries),
    )


def retrying_completion(client, *, via: str, max_retries: int, **create_kwargs) -> dict:
    """Call `client.chat.completions.create(**create_kwargs)`, retrying up to
    `max_retries` times (i.e. `max_retries + 1` total attempts) while the
    classified reply is `degraded`.

    `max_retries` is the SAME `llm_client.max_retries` value passed to the
    `OpenAI()` client constructor for SDK transport-level retries (429/500/
    503) — one configured budget governs both layers, deliberately: two
    separate knobs for "how hard do we try" (one wired to config, one
    hardcoded) is the exact kind of drift this fix exists to remove (AC1).
    Worst case combined network calls is bounded at `(max_retries + 1) ** 2`
    (9-36 for typical values of 2-5) — and rarely reached in practice, because
    a persistent transport fault almost always ends by the SDK *raising* once
    its own budget is exhausted (see below, not retried here), rather than by
    returning HTTP 200 with degraded content on every attempt. The narrow
    tail this bound actually covers is a fault that keeps resolving to
    "200 OK, but empty/truncated content" across several attempts.

    Scope: this retries ONLY the "200 OK but degraded classification" case
    (empty/truncated content) — a provider returning HTTP 200 with a blank
    `message.content` is not an HTTP transport error, so the SDK's own
    transport-level retry never sees it; `classify_reply` is the only place
    that can tell. A raised exception (on any attempt, including the last) is
    NOT retried here — it propagates to the caller's existing
    `except Exception` handler unchanged, exactly as before this function
    existed. Without this loop a single transient empty reply became the
    final, permanent result for the whole review pass (observed: DeepSeek's
    arm silently degraded across every sampled iterate run from 2026-08-13 to
    2026-08-31 while GPT carried the cascade alone).
    """
    result = {"status": "degraded", "reason": "no attempt made", "via": via}
    for _attempt in range(max_retries + 1):
        response = client.chat.completions.create(**create_kwargs)
        result = classify_reply(
            response.choices[0].message.content,
            openai_finish_reason(response),
            via=via,
        )
        if result["status"] != "degraded":
            break
    return result


def file_partial_degradation_triage(
    project_root, run_id: str | None, mode: str, provider: str, legs: list[str],
) -> None:
    """Auto-file a triage card when a reviewer arm degraded silently.

    Best-effort and never fatal: a triage-filing failure must not affect the
    review gate's own exit code. Idempotent per (provider, leg) per 24h via
    `append_triage_item_idempotent`'s `dedup_key` — the same daily-re-flag
    convention the Phase-Quality producer uses — so a run of repeated
    failures doesn't spam the tracked log with one card per invocation.

    Each leg is filed independently (its own try/except): one leg's filing
    failure must not suppress filing for the others.
    """
    _scripts_dir = str(Path(__file__).resolve().parents[1])
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
    for leg in legs:
        try:
            from triage import append_triage_item_idempotent, should_route_to_outbox

            append_triage_item_idempotent(
                project_root,
                source="external_review_degradation",
                severity="medium",
                kind="maintenance",
                title=f"External review: {leg} reviewer degraded during {mode} review",
                detail=(
                    f"The {leg} reviewer arm did not return a usable reply during an "
                    f"external {mode} review (provider={provider}), while at least "
                    "one other reviewer succeeded. The review gate still passed on "
                    f"the other reviewer's opinion, so nothing was blocked — but "
                    f"{leg}'s review was silently missing from this pass. If this "
                    "recurs across runs, the reviewer arm's routing/reliability is "
                    "worth investigating."
                ),
                dedup_key=f"{provider}:{leg}",
                match_commit=False,
                run_id=run_id,
                to_outbox=should_route_to_outbox(project_root),
            )
        except Exception as exc:  # noqa: BLE001 — best-effort, never blocks the gate
            print(f"note: could not auto-file triage for {leg!r}: {exc}", file=sys.stderr)


def finalize_review_output(provider: str, reviews: dict) -> tuple[dict, int]:
    """Build the stable CLI payload and fail loudly on total provider failure."""
    succeeded = count_succeeded(reviews)
    degraded = is_degraded(provider, reviews)
    output: dict = {
        # Version 1 was implicit and used the historical gemini/openai roster.
        # Version 2 makes the non-gemini roster change explicit — originally
        # deepseek/openai, now glm/openai (lib.review_payloads accepts both
        # under schema 2, since the envelope SHAPE didn't change either time).
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
    elif is_partially_degraded(provider, reviews):
        legs = partially_degraded_legs(reviews)
        output["partially_degraded"] = True
        output["partially_degraded_legs"] = legs
        print(_PARTIAL_BANNER.format(legs=", ".join(legs)), file=sys.stderr)
    return output, (1 if degraded else 0)

"""Degraded-gate detection for external_review.py (SS6).

The external review CLI must never silently no-op. ``main()`` used to hardcode
``success: true`` regardless of whether any review actually ran, so when keys
were present but every leg failed (e.g. Gemini key missing + the direct OpenAI
call erroring on an incompatible param) the caller saw ``success: true`` with no
feedback and marked the gate "completed" — a silent fall-back to self-review.

This module computes the degraded condition and shapes the CLI's final output +
process exit code so the failure is LOUD: ``success: false``, a machine-readable
``degraded`` flag + ``degraded_reason``, a stderr banner, and a non-zero exit
code. It lives in its own module so the review CLI stays under its size budget
and the gate logic is unit-testable in isolation.

``provider == "none"`` (no keys at all) is NOT degraded: that is the explicit
missing-keys state the caller already handles via
``get_external_review_status`` (Branch B). Degradation means a provider was
attempted but produced zero successful reviews.
"""

from __future__ import annotations

import sys

# Providers that mean "keys are present, a real review was attempted".
_ATTEMPTED_PROVIDERS = ("openrouter", "direct")

_BANNER = (
    "error: external review gate DEGRADED — API keys are present but no review "
    "succeeded ({reason}). This is NOT a silent skip: the caller must treat it "
    "as 'external review did not run' (re-check keys / self-review fallback), "
    "not mark the gate completed."
)


# --- Is this reply actually a review? (iterate-2026-07-27-name-the-blocker) ---
#
# A leg used to be recorded ``success`` whenever the HTTP call returned. On one
# observed run the Gemini leg came back with an unfinished internal monologue
# while the transport reported success, so the gate counted a review that had not
# happened. Only two signals are used, and both are stated by the provider
# itself — an empty answer, and a declared truncation. No prose heuristic decides
# whether text "reads like a review": that would eventually reject a real one.

#: Known provider terminal reasons that mean no complete review was delivered.
_DEGRADED_FINISH_REASONS = frozenset({
    "length", "max_tokens", "maxtokens", "content_filter", "safety", "recitation", "language", "other",
    "blocklist", "prohibited_content", "spii", "malformed_function_call", "image_safety", "image_prohibited_content",
    "no_image", "image_recitation", "image_other", "unexpected_tool_call", "too_many_tool_calls", "tool_calls", "function_call",
})


# --- How much room the reply gets (iterate-2026-08-01-llm-review-truncation-guard) ---
#
# Reasoning tokens are billed against the SAME ceiling as visible output. On a
# 209,549-char review prompt against google/gemini-3.1-pro-preview:
#
#   max_tokens  reasoning cap  reasoning_tokens    visible chars  finish_reason
#   4096        none           3928 / 4092         621            length
#   16000       none           15360 / 15996       2352           length
#   16000       2000           3332                13448          stop
#   16000       2000           3791                14134          stop
#   16000       2000           6909                14077          stop
#
# What that does and does NOT establish: the loose version ("the model burns
# ~96% of any ceiling") is a stronger law than the
# data supports and would mislead the next editor:
#
# 1. On BOTH uncapped runs reasoning consumed essentially the entire ceiling and
#    the answer was truncated. That is measured. Whether the burn scales with
#    the ceiling, or simply exceeds every ceiling tested, is NOT distinguished
#    by these points — but either reading gives the same conclusion: raising the
#    total alone did not fix it at 4x, so the cap is doing real work.
# 2. The cap is WEAK, not exact. Same cap of 2000 produced 3332, 3791 and 6909
#    across three runs — a 1.7x to 3.5x overshoot with 2x run-to-run variance.
#    So the total must absorb a multiple of the cap, not cap + answer. That
#    variance is the whole reason 16000 is not over-generous: at 6909 reasoning
#    plus a ~3500-token answer, a smaller ceiling truncates again.
#
# These two numbers are a COUPLED PAIR, and the coupling is ABSOLUTE, not a
# ratio: `test_external_review_budget.py` pins that the total leaves room for a
# 3.5x-overshot cap PLUS a full answer, because a pure ratio invariant is
# satisfied by (4096, 1024) — which reproduces the original bug exactly.
#
# Deliberately constants rather than config keys: two independent knobs would
# let an operator set a cap that eats the ceiling, silently restoring the
# fail-open with no gate to catch it (see the mini-plan's rejected alternative).
#
# SCOPE OF THE EVIDENCE, stated so the next editor does not over-read it: the
# cap was chosen to stop TRUNCATION, and was never measured against finding
# YIELD (unique HIGH findings per run — the metric that justified this work).
# If yield drops on the Gemini leg, the cap is the first thing to move — but
# raise the TOTAL with it: at the measured 3.5x overshoot a cap of 4000 could
# consume 14000 of 16000, leaving less than a full answer. The headroom under
# this total runs out at a cap of roughly 3500; beyond that, both numbers move.
# `test_the_invariant_rejects_the_values_that_reproduce_the_bug` asserts exactly
# that, in both directions.
MAX_OUTPUT_TOKENS = 16000
REASONING_MAX_TOKENS = 2000

#: Seconds to wait for a review call. Coupled to MAX_OUTPUT_TOKENS: a bigger
#: budget takes longer to generate, so raising one without the other converts a
#: partial review into no review. Measured at 89.2s for a 10500-token
#: completion, hence 240 rather than the previous 120. Kept in lockstep with
#: shared/config/external_review.json's llm_client.timeout_seconds by
#: test_llm_review.py::test_default_timeout_matches_shipping_config.
DEFAULT_TIMEOUT_SECONDS = 240


def openrouter_extra_body(model_key: str) -> dict:
    """OpenRouter ``extra_body`` bounding reasoning — for the Gemini arm only.

    Returns ``{}`` for every other arm. The cap is applied exactly where it was
    demonstrated to be needed, and nowhere else:

    * ``gemini`` — unbounded, this arm consumed the whole ceiling at 4096 AND at
      16000 and truncated both times. It needs the cap.
    * ``openai`` (``gpt-5.6-terra``) — never truncated at 4096. Measured with and
      without the cap on the same 209k-char prompt: reasoning 1235 vs 1220, 33
      findings both times, ``finish_reason=stop`` both times. But that shows the
      cap is *non-binding on that prompt*, which is NOT the same as harmless on
      a prompt where GPT wants more than ``REASONING_MAX_TOKENS`` — OpenRouter
      may normalise the field into a provider effort tier, and a shallower tier
      would quietly reduce depth on the highest-yield review pass in the fleet.
      Rather than ship an unmeasurable risk for a benefit this arm was never
      shown to need, the cap is simply not sent here. Raising the total budget
      already gives it more headroom than it had.

    (``openai/gpt-4o-mini``, a non-reasoning model, does accept the field
    without error — so this is a deliberate scoping decision, not a
    compatibility workaround.)
    """
    if model_key != "gemini":
        return {}
    return {"reasoning": {"max_tokens": REASONING_MAX_TOKENS}}


def _is_http_400(exc: Exception) -> bool:
    """True only when the provider explicitly rejected the request shape."""
    status = getattr(exc, "status_code", getattr(exc, "code", None))
    try:
        return int(status) == 400
    except (TypeError, ValueError):
        return False


def gemini_generate(genai, client, model_name: str, prompt: str, system_prompt: str):
    """Direct-Gemini call carrying an explicit thinking budget.

    Returns ``(response, fallback_note)``. ``fallback_note`` is ``None`` on the
    normal path and a one-line reason when the reasoning cap had to be dropped —
    callers merge it into the classified reply so the condition survives into
    ``reviews.json`` / ``review.md``. A stderr line alone would not: no
    machine-readable consumer captures stderr, and this module's whole charter
    is that a degraded gate is LOUD and inspectable after the fact.

    Retries **once** without ``thinking_config`` only for local config-shape
    failures or provider HTTP 400. Config construction and the network call use
    separate ``try`` blocks: an accidental ``AttributeError`` from provider
    code must not look like an old-SDK incompatibility and re-bill the prompt.

    Lives here rather than in each caller so the two review paths cannot drift
    apart again — that divergence is exactly what this module was written for.
    """

    def _config(with_thinking: bool):
        kwargs: dict = {
            "system_instruction": system_prompt,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        }
        if with_thinking:
            kwargs["thinking_config"] = genai.types.ThinkingConfig(
                thinking_budget=REASONING_MAX_TOKENS
            )
        return genai.types.GenerateContentConfig(**kwargs)

    def _without_reasoning(exc: Exception):
        note = (
            f"reasoning cap dropped: first attempt failed ({type(exc).__name__}: "
            f"{exc}); retried with reasoning UNBOUNDED"
        )
        print(f"warning: {note}", file=sys.stderr)
        try:
            return client.models.generate_content(
                model=model_name, contents=prompt, config=_config(False)
            ), note
        except Exception as retry_exc:  # noqa: BLE001 — preserve both failures
            raise RuntimeError(
                f"{note}; retry failed ({type(retry_exc).__name__}: {retry_exc})"
            ) from retry_exc

    try:
        config = _config(True)
    except (AttributeError, TypeError, ValueError) as exc:
        return _without_reasoning(exc)

    try:
        return client.models.generate_content(
            model=model_name, contents=prompt, config=config
        ), None
    except Exception as exc:  # noqa: BLE001 — status is checked below
        if not _is_http_400(exc):
            raise
        return _without_reasoning(exc)

def _normalize_finish_reason(raw: object) -> str:
    """Lower-cased bare reason. Handles a plain string and google-genai's enum,
    whose ``str()`` renders as ``FinishReason.MAX_TOKENS``."""
    if raw is None:
        return ""
    name = getattr(raw, "name", None)
    text = name if isinstance(name, str) else str(raw)
    return text.rsplit(".", 1)[-1].strip().lower()


def openai_finish_reason(response: object) -> str:
    """``choices[0].finish_reason`` (OpenAI / OpenRouter), or ``""``."""
    try:
        return str(response.choices[0].finish_reason or "")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — an unreadable reason is simply unknown
        return ""


def gemini_finish_reason(response: object) -> str:
    """``candidates[0].finish_reason`` (Gemini direct), or ``""``."""
    try:
        raw = response.candidates[0].finish_reason  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — an unreadable reason is simply unknown
        return ""
    if raw is None:
        return ""
    name = getattr(raw, "name", None)
    return name if isinstance(name, str) else str(raw)


def classify_reply(text: str | None, finish_reason: object, *, via: str) -> dict:
    """Shape one provider leg's outcome: ``success`` or ``degraded`` + a reason.

    A degraded leg still carries whatever text arrived — a human reading the run
    should see the partial answer, not just be told it was discarded. An absent
    or unrecognised ``finish_reason`` is neutral: missing metadata is not
    evidence of truncation.
    """
    base = {"feedback": text, "via": via}
    if not (text or "").strip():
        return {**base, "status": "degraded", "reason": "provider returned an empty reply"}
    if _normalize_finish_reason(finish_reason) in _DEGRADED_FINISH_REASONS:
        return {
            **base, "status": "degraded",
            "reason": (
                "provider reported the reply was cut off or otherwise incomplete "
                f"(finish_reason={finish_reason})"
            ),
        }
    return {**base, "status": "success"}


def count_succeeded(reviews: dict) -> int:
    """Number of reviews whose status is ``success``."""
    return sum(1 for r in reviews.values() if r.get("status") == "success")


def is_degraded(provider: str, reviews: dict) -> bool:
    """True iff a provider was attempted but zero reviews succeeded."""
    return provider in _ATTEMPTED_PROVIDERS and count_succeeded(reviews) == 0


def degraded_reason(provider: str, reviews: dict) -> str:
    """One-liner explaining the degradation, per-leg (human + machine readable)."""
    parts = "; ".join(
        f"{name}: {r.get('reason', r.get('status', 'unknown'))}"
        for name, r in sorted(reviews.items())
    )
    return f"provider={provider} but 0/{len(reviews)} reviews succeeded ({parts})"


def finalize_review_output(provider: str, reviews: dict) -> tuple[dict, int]:
    """Build the CLI's final JSON payload + process exit code.

    Emits a stderr banner and returns exit code ``1`` when the gate is degraded
    so a silent no-op is impossible. Healthy / no-keys / partial-success runs
    return exit code ``0`` with ``success: true``.
    """
    succeeded = count_succeeded(reviews)
    degraded = is_degraded(provider, reviews)

    output: dict = {
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

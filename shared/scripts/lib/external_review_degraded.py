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

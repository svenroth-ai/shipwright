"""Envelope for a code-mode review whose diff is empty (no provider is called)."""

from __future__ import annotations

from typing import Any

# Bare imports on purpose: only tools/external_review.py imports this, and it puts
# shared/scripts/lib on sys.path (no lib.-qualified fallback needed).

from external_review_degraded import REVIEW_ENVELOPE_SCHEMA
from external_review_gateway import gateway_configured
from external_review_routing import DRIVER_ROSTERS
from review_verdict import GATEWAY_REVIEWERS, summarize_reviews

__all__ = ["empty_diff_envelope"]


def empty_diff_envelope(driver: str, driver_record: dict[str, Any]) -> dict[str, Any]:
    """The LLM cannot review what isn't there, and many providers reject empty
    inputs. Built from the selected roster (not hardcoded glm/openai) so a
    ``--driver codex`` run skips {glm, opus}, not a nonexistent "openai" leg."""
    roster = GATEWAY_REVIEWERS if gateway_configured() else DRIVER_ROSTERS[driver]
    reviews = {name: {"status": "skipped", "reason": "empty diff"} for name in roster}
    return {
        "review_schema": REVIEW_ENVELOPE_SCHEMA,
        "success": True,
        "skipped": "empty_diff",
        "provider": "none",
        **driver_record,
        "degraded": False,
        "reviewed": False,  # nothing was sent anywhere: success without a review
        "reviews": reviews,
        # Same shape on every exit path so a consumer never has to guard
        # for the block's absence.
        **summarize_reviews(reviews),
    }

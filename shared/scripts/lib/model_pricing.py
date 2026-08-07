"""$/MTok pricing table + cost computation for the context-cost meter.

Rates: base input/output from the Anthropic Current Models table (cached
2026-06-24); cache economics from ``shared/prompt-caching.md`` Sec Economics —
cache-read = 0.1x base input, cache-write = 1.25x base input for the 5-minute
TTL, 2x for the 1-hour TTL. Sonnet 5 uses its STANDARD post-intro rate here,
not the $2/$10 introductory window that expires 2026-08-31 — a durable meter
hardcoding an expiring rate would silently under-report from that date on;
standard rates instead over-report for a few weeks, the safe direction for a
tool whose purpose is flagging cost pressure.

No cross-model fallback, ever (context-cost-meter design correction after
operator review): :func:`compute_cost_usd` returns ``(None, True)`` for a
model id it cannot match, exactly and after stripping a versioned
``-YYYYMMDD`` date suffix. Pricing an unrecognized model at another model's
rate is a plausible-but-wrong number — the same failure mode that put two
prior cost investigations off by 2x.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["ModelPrice", "MODEL_PRICING", "compute_cost_usd", "resolve_model_id"]


@dataclass(frozen=True)
class ModelPrice:
    input: float
    output: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float


def _priced(input_rate: float, output_rate: float) -> ModelPrice:
    return ModelPrice(
        input=input_rate,
        output=output_rate,
        cache_write_5m=round(input_rate * 1.25, 6),
        cache_write_1h=round(input_rate * 2, 6),
        cache_read=round(input_rate * 0.1, 6),
    )


MODEL_PRICING: dict[str, ModelPrice] = {
    "claude-opus-5": _priced(5.00, 25.00),
    "claude-sonnet-5": _priced(3.00, 15.00),
    "claude-haiku-4-5": _priced(1.00, 5.00),
}

_DATE_SUFFIX = re.compile(r"-\d{8}$")


def resolve_model_id(model: str) -> str | None:
    """Exact match, else a dated-snapshot match of a KNOWN family, else None.

    Stripping ``-YYYYMMDD`` recognizes a versioned snapshot of a model
    already in the table (e.g. ``claude-sonnet-5-20260612``) — it is not a
    guess across different models, so it does not violate the no-fallback
    rule. A real transcript records the versioned id, not the bare family
    name; without this, every real call would come back unpriced.

    Returns the CANONICAL family name (a ``MODEL_PRICING`` key), not the
    input verbatim, so a caller matching against another table keyed the
    same way (``context_cost_readiness.MODEL_CONTEXT_WINDOWS``) can reuse
    this exact policy instead of re-deriving its own date-strip regex —
    external review on iterate-2026-08-07-context-cost-meter found the
    readiness check's own copy missing this, so a real dated snapshot id
    read back "not a known model" instead of being checked.
    """
    if model in MODEL_PRICING:
        return model
    stripped = _DATE_SUFFIX.sub("", model)
    if stripped != model and stripped in MODEL_PRICING:
        return stripped
    return None


def _resolve_price(model: str) -> ModelPrice | None:
    canonical = resolve_model_id(model)
    return MODEL_PRICING.get(canonical) if canonical is not None else None


def _num(value) -> int | float:
    """Coerce a usage token-count field to a non-negative number, or 0.

    Mirrors context_cost_core._num exactly (same fix, duplicated rather
    than cross-imported to avoid a lib-to-lib coupling neither module
    otherwise needs): a malformed value degrades to 0 for that token type
    instead of raising a TypeError out of the whole cost calculation
    (external-review finding, iterate-2026-08-07-context-cost-meter).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return value if value >= 0 else 0


def compute_cost_usd(model: str, usage: dict) -> tuple[float | None, bool]:
    """Return ``(cost_usd, unpriced)`` for one call's token usage.

    Each token type is priced at its own rate and summed — never a blended
    "total tokens x input rate" (cache reads were measured at 82% of actual
    bill; blending them into the input rate overstates cost by roughly an
    order of magnitude). ``usage`` is read defensively: missing fields are
    treated as zero, never as an error — a genuinely unrecognized MODEL is
    the only condition that yields ``unpriced``.

    Cache-write token handling: the TTL-split fields
    (``cache_creation.ephemeral_5m_input_tokens`` /
    ``ephemeral_1h_input_tokens``) are used when present. When only the
    older aggregate ``cache_creation_input_tokens`` is present (no split),
    it is priced at the 5-minute TTL rate — the API's documented default
    when no TTL is requested. The two are never both counted: a present
    split always wins over the aggregate, so a transcript record carrying
    both is never double-priced. "Present" means the KEY exists, not that
    its value is truthy — a real record can legitimately carry
    ``{"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}``
    for a call that wrote nothing to cache, and that must still win over a
    stale/duplicated aggregate field rather than silently falling through
    to it (external-review finding, iterate-2026-08-07-context-cost-meter).
    """
    # model must be a string, not merely truthy -- an unhashable value (e.g.
    # a list) would raise out of the MODEL_PRICING dict lookup below rather
    # than degrading to "unpriced" like every other unrecognized model does
    # (external-review finding, iterate-2026-08-07-context-cost-meter).
    if not isinstance(model, str):
        return None, True

    price = _resolve_price(model)
    if price is None:
        return None, True

    input_tokens = _num(usage.get("input_tokens"))
    output_tokens = _num(usage.get("output_tokens"))
    cache_read_tokens = _num(usage.get("cache_read_input_tokens"))

    cache_creation = usage.get("cache_creation")
    if not isinstance(cache_creation, dict):
        cache_creation = {}
    split_present = (
        "ephemeral_5m_input_tokens" in cache_creation
        or "ephemeral_1h_input_tokens" in cache_creation
    )
    write_5m = _num(cache_creation.get("ephemeral_5m_input_tokens"))
    write_1h = _num(cache_creation.get("ephemeral_1h_input_tokens"))
    if not split_present:
        # No TTL split key present — fall back to the aggregate, priced at
        # the documented 5m default. Never added on top of a present split.
        write_5m = _num(usage.get("cache_creation_input_tokens"))

    cost = (
        input_tokens * price.input
        + output_tokens * price.output
        + cache_read_tokens * price.cache_read
        + write_5m * price.cache_write_5m
        + write_1h * price.cache_write_1h
    ) / 1_000_000

    # Full precision, NOT rounded here: a single cache-read token can cost
    # under $0.000001 (Sonnet 5: $0.0000003), which rounds to exactly 0.0 at
    # 6dp. Every caller of this function accumulates many calls into a
    # total -- rounding per call before summing silently discards real cost
    # from any total built out of many sub-microdollar calls, even though
    # the SUM would be well above the rounding threshold. Round once, at
    # the point a total is finalized for persistence/display (external-
    # review finding, iterate-2026-08-07-context-cost-meter).
    return cost, False

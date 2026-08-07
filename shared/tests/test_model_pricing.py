"""Tests for the context-cost $/MTok pricing table and cost computation.

No cross-model fallback: an unrecognized model id must return ``(None, True)``,
never another model's price (context-cost-meter, per operator correction after
a prior draft's blended-rate / silent-fallback design was rejected in review).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import model_pricing as mp  # noqa: E402


def test_pricing_table_has_the_three_current_models():
    for model_id in ("claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"):
        assert model_id in mp.MODEL_PRICING


def test_opus_5_rates_match_current_models_table():
    price = mp.MODEL_PRICING["claude-opus-5"]
    assert price.input == 5.00
    assert price.output == 25.00
    assert price.cache_write_5m == 6.25
    assert price.cache_write_1h == 10.00
    assert price.cache_read == 0.50


def test_sonnet_5_rates_are_standard_not_intro():
    price = mp.MODEL_PRICING["claude-sonnet-5"]
    assert price.input == 3.00
    assert price.output == 15.00


def test_cost_prices_each_token_type_at_its_own_rate():
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 1_000_000,
            "ephemeral_1h_input_tokens": 1_000_000,
        },
    }
    cost, unpriced = mp.compute_cost_usd("claude-opus-5", usage)
    assert unpriced is False
    # 5 + 25 + 0.5 + 6.25 + 10 = 46.75
    assert cost == 46.75


def test_cache_read_only_usage_prices_at_cache_read_rate_not_input_rate():
    """Regression guard: the 82%-of-bill finding — cache reads must never be
    priced as plain input tokens."""
    usage = {"cache_read_input_tokens": 1_000_000}
    cost, unpriced = mp.compute_cost_usd("claude-sonnet-5", usage)
    assert unpriced is False
    assert cost == 0.30  # cache-read rate, NOT the $3.00 input rate


def test_aggregate_cache_creation_without_ttl_split_prices_at_5m_default():
    usage = {"cache_creation_input_tokens": 1_000_000}
    cost, unpriced = mp.compute_cost_usd("claude-opus-5", usage)
    assert unpriced is False
    assert cost == 6.25  # 5m TTL is the documented default when unspecified


def test_split_and_aggregate_present_together_does_not_double_count():
    usage = {
        "cache_creation_input_tokens": 1_000_000,
        "cache_creation": {"ephemeral_5m_input_tokens": 1_000_000},
    }
    cost, unpriced = mp.compute_cost_usd("claude-opus-5", usage)
    assert unpriced is False
    assert cost == 6.25  # split wins; aggregate is not added on top


def test_ttl_split_present_with_explicit_zero_wins_over_a_nonzero_aggregate():
    """Regression guard (external review): presence of the split KEY wins,
    not the split value's truthiness. A record can legitimately carry an
    explicit-zero split alongside a stale/duplicated nonzero aggregate, and
    the split (zero) must still win rather than falling through to it."""
    usage = {
        "cache_creation_input_tokens": 1_000_000,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 0,
            "ephemeral_1h_input_tokens": 0,
        },
    }
    cost, unpriced = mp.compute_cost_usd("claude-opus-5", usage)
    assert unpriced is False
    assert cost == 0.0  # split (explicitly zero) wins; aggregate never used


def test_resolve_model_id_exact_and_date_suffix_stripped():
    assert mp.resolve_model_id("claude-sonnet-5") == "claude-sonnet-5"
    assert mp.resolve_model_id("claude-sonnet-5-20260612") == "claude-sonnet-5"
    assert mp.resolve_model_id("claude-nonexistent-9") is None
    assert mp.resolve_model_id("claude-nonexistent-9-20260101") is None


def test_versioned_model_id_resolves_via_date_suffix_stripping():
    usage = {"input_tokens": 1_000_000}
    cost, unpriced = mp.compute_cost_usd("claude-sonnet-5-20260612", usage)
    assert unpriced is False
    assert cost == 3.00


def test_unrecognized_model_returns_none_never_another_models_price():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    cost, unpriced = mp.compute_cost_usd("claude-nonexistent-9", usage)
    assert cost is None
    assert unpriced is True


def test_unrecognized_versioned_model_also_returns_none():
    usage = {"input_tokens": 1_000_000}
    cost, unpriced = mp.compute_cost_usd("claude-nonexistent-9-20260101", usage)
    assert cost is None
    assert unpriced is True


def test_zero_usage_is_zero_cost_not_unpriced():
    cost, unpriced = mp.compute_cost_usd("claude-haiku-4-5", {})
    assert unpriced is False
    assert cost == 0.0


def test_unhashable_model_degrades_to_unpriced_not_a_crash():
    # External-review finding: an unhashable model value used to raise a
    # TypeError out of the MODEL_PRICING dict lookup, instead of degrading
    # to unpriced like every other unrecognized model.
    cost, unpriced = mp.compute_cost_usd(["not", "a", "string"], {"input_tokens": 100})
    assert cost is None
    assert unpriced is True


def test_non_numeric_token_field_degrades_that_field_to_zero_not_a_crash():
    # External-review finding: a string input_tokens value used to raise a
    # TypeError out of the whole cost calculation instead of the malformed
    # field degrading to 0 for that one token type.
    usage = {"input_tokens": "one hundred", "output_tokens": 1_000_000}
    cost, unpriced = mp.compute_cost_usd("claude-opus-5", usage)
    assert unpriced is False
    assert cost == 25.00  # input_tokens ignored (malformed), output priced normally


def test_many_sub_microdollar_calls_are_not_individually_rounded_to_zero():
    # External-review finding: compute_cost_usd used to round each call to
    # 6dp before returning, zeroing out a single cache-read token
    # ($0.0000003 on Sonnet 5) even though many such calls summed by a
    # caller would be well above the rounding threshold.
    cost, unpriced = mp.compute_cost_usd("claude-sonnet-5", {"cache_read_input_tokens": 1})
    assert unpriced is False
    assert cost > 0.0

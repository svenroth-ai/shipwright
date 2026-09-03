"""``external_review.gpt_leg.provider`` config resolution, and the Codex
identity-lock binding it feeds into ``resolve_reviewer_model``."""

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from external_review_config import gpt_leg_provider  # noqa: E402
from external_review_default_legs import (  # noqa: E402
    CODEX_DEFAULT_MAX_RETRIES,
    CODEX_DEFAULT_TIMEOUT_SECONDS,
    codex_settings,
)
from external_review_routing import ReviewModelPolicyError, resolve_reviewer_model  # noqa: E402


def test_gpt_leg_provider_defaults_to_api_when_unset():
    assert gpt_leg_provider({}) == "api"
    assert gpt_leg_provider({"external_review": {}}) == "api"


def test_gpt_leg_provider_reads_the_configured_value():
    config = {"external_review": {"gpt_leg": {"provider": "codex"}}}
    assert gpt_leg_provider(config) == "codex"


def test_gpt_leg_provider_falls_back_to_api_on_an_unrecognized_value():
    config = {"external_review": {"gpt_leg": {"provider": "carrier-pigeon"}}}
    assert gpt_leg_provider(config) == "api"


def test_gpt_leg_provider_falls_back_to_api_on_a_mis_shaped_gpt_leg():
    """A plausible typo — `gpt_leg` as a bare string instead of {"provider": ...}
    — must degrade to the safe default, not raise AttributeError out of the
    review gate."""
    assert gpt_leg_provider({"external_review": {"gpt_leg": "codex"}}) == "api"
    assert gpt_leg_provider({"external_review": {"gpt_leg": None}}) == "api"


def test_gpt_leg_provider_falls_back_to_api_on_an_unhashable_value():
    """A malformed override — `"provider": []` or `{}` — must degrade to the safe default,
    not raise TypeError out of `value in _GPT_LEG_PROVIDERS` (unhashable types can't be
    tested for set membership)."""
    assert gpt_leg_provider({"external_review": {"gpt_leg": {"provider": []}}}) == "api"
    assert gpt_leg_provider({"external_review": {"gpt_leg": {"provider": {}}}}) == "api"


def test_codex_binding_accepts_the_locked_model():
    config = {"models": {"codex": "gpt-5.6-terra"}}
    assert resolve_reviewer_model(config, "openai", "codex") == "gpt-5.6-terra"


def test_codex_binding_rejects_a_different_configured_model():
    config = {"models": {"codex": "some-other-model"}}
    try:
        resolve_reviewer_model(config, "openai", "codex")
        raise AssertionError("expected ReviewModelPolicyError")
    except ReviewModelPolicyError as exc:
        assert "must use" in str(exc)


def test_codex_settings_falls_back_to_defaults_on_a_non_mapping_codex_config():
    """A malformed override — `"codex": []` — must degrade to defaults, not raise
    AttributeError out of `codex_cfg.get(...)` (a list has no `.get`)."""
    assert codex_settings({"codex": []}) == (CODEX_DEFAULT_TIMEOUT_SECONDS, CODEX_DEFAULT_MAX_RETRIES)
    assert codex_settings({"codex": "not-a-mapping"}) == (CODEX_DEFAULT_TIMEOUT_SECONDS, CODEX_DEFAULT_MAX_RETRIES)


def test_codex_binding_shares_the_openai_identity_and_model_with_the_api_routes():
    """Same reviewer ('openai'), same model string, across all three routes —
    a mixed pass (e.g. codex answers this run, openrouter answered last run)
    must not read as two different reviewers."""
    config = {"models": {"chatgpt": "gpt-5.6-terra", "openrouter_chatgpt": "openai/gpt-5.6-terra", "codex": "gpt-5.6-terra"}}
    assert resolve_reviewer_model(config, "openai", "direct") == "gpt-5.6-terra"
    assert resolve_reviewer_model(config, "openai", "codex") == "gpt-5.6-terra"

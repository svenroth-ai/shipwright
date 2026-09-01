"""GLM 5.3 ZDR routing contract for the PR-review gate's default model.

Mirrors test_deepseek_review_routing.py's DeepSeek coverage for the parallel
`glm_routing` config block and `glm_openrouter_extra_body()` function added
alongside the GLM 5.3 default-model swap (iterate-2026-09-01-pr-review-glm-model).
Scoped to the shared routing module only — the PR-review gate's own
dispatch/short-circuit behavior is covered in
plugins/shipwright-security/tests/test_pr_review_model_policy.py and
test_pr_review_deepseek_routing.py.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
for _path in (_SHARED / "scripts" / "tools", _SHARED / "scripts" / "lib"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from external_review_config import load_review_config  # noqa: E402
from external_review_routing import (  # noqa: E402
    APPROVED_GLM_ENDPOINTS,
    GlmRoutingPolicyError,
    glm_openrouter_extra_body,
)

EXPECTED_PROVIDER = {
    "only": ["novita", "together"],
    "order": ["novita", "together"],
    "allow_fallbacks": False,
    "data_collection": "deny",
    "zdr": True,
}


def test_shipping_config_builds_the_exact_fail_closed_policy():
    config = load_review_config()
    assert APPROVED_GLM_ENDPOINTS == (("novita", "US"), ("together", "US"))
    assert glm_openrouter_extra_body(config) == {"provider": EXPECTED_PROVIDER}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.pop("glm_routing"),
        lambda c: c["glm_routing"].update(provider_allowlist=[]),
        lambda c: c["glm_routing"]["provider_allowlist"].reverse(),
        lambda c: c["glm_routing"]["provider_allowlist"].pop(),
        lambda c: c["glm_routing"]["provider_allowlist"].append(
            {"provider": "glm-vendor", "region": "CN", "zero_retention_verified": True}
        ),
        lambda c: c["glm_routing"]["provider_allowlist"][0].update(region="SG"),
        lambda c: c["glm_routing"]["provider_allowlist"][0].update(
            zero_retention_verified=False
        ),
        lambda c: c["glm_routing"]["provider_allowlist"][0].pop("zero_retention_verified"),
        lambda c: c["glm_routing"]["provider_allowlist"].__setitem__(0, "not-an-object"),
        lambda c: c["glm_routing"]["provider_allowlist"][0].pop("provider"),
    ],
)
def test_changed_or_unverified_provider_config_fails_closed(mutate):
    config = copy.deepcopy(load_review_config())
    mutate(config)
    with pytest.raises(GlmRoutingPolicyError):
        glm_openrouter_extra_body(config)


def test_glm_and_deepseek_routing_errors_are_distinct_types():
    # The generic helper must not blur which family failed — a caller
    # narrowing an except clause on one must not silently swallow the other.
    from external_review_routing import DeepSeekRoutingPolicyError

    assert not issubclass(GlmRoutingPolicyError, DeepSeekRoutingPolicyError)
    assert not issubclass(DeepSeekRoutingPolicyError, GlmRoutingPolicyError)

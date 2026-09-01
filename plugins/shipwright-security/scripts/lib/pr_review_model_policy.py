"""Model-identity policy for the Tier-3 PR reviewer's OpenRouter call.

Owns the ONE decision this gate needs beyond a bare model string: whether the
resolved `SHIPWRIGHT_PR_REVIEW_MODEL` is in a ZDR-gated vendor namespace
(`deepseek/`, the operator-overridable arm; `z-ai/`, the default since
iterate-2026-09-01-pr-review-glm-model) and, if so, must carry
`shared/scripts/lib/external_review_routing`'s fail-closed ZDR provider-routing
constraint — the same one already enforced for the review cascade's DeepSeek
arm (`shared/config/external_review.json`).

Deliberately NOT an allowlist: per ADR-167, this gate's model is meant to stay
freely operator-overridable ("allows a model switch via
SHIPWRIGHT_PR_REVIEW_MODEL"). An override outside both gated namespaces — a
Sonnet rollback, a one-off experiment — must resolve to `{}` WITHOUT ever
importing or loading `external_review.json`, so a broken/absent review config
cannot break PR review for a model that never needed it
(iterate-2026-08-31-pr-review-deepseek-model, independently found by both the
internal and the external plan review).

Kept out of `pr_review_openrouter.py`, which is documented as the pure HTTP
boundary ("stdlib urllib only") — this module is the one place in this tool
that reaches into `shared/scripts/lib`, matching how every other tool in this
plugin wires that import from the tool/lib layer, not from inside another
lib module (ADR-045: `shared/scripts/lib` is itself a package with common
module names that can shadow under a different test root).
"""

from __future__ import annotations

import sys
from pathlib import Path

# parents[0]=lib, [1]=scripts, [2]=security plugin root, [3]=plugins, [4]=repo root.
_SHARED_LIB = Path(__file__).resolve().parents[4] / "shared" / "scripts" / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from external_review_config import load_review_config  # noqa: E402
from external_review_routing import (  # noqa: E402
    DeepSeekRoutingPolicyError,
    GlmRoutingPolicyError,
    deepseek_openrouter_extra_body,
    glm_openrouter_extra_body,
)

__all__ = [
    "DeepSeekRoutingPolicyError",
    "GlmRoutingPolicyError",
    "is_deepseek_model",
    "is_glm_model",
    "resolve_extra_body",
]


def is_deepseek_model(model: str) -> bool:
    """True if `model` names an OpenRouter model in the `deepseek/` namespace.

    Normalized (trimmed, casefolded) and namespace-matched rather than an
    exact-string comparison — a variant suffix (`:free`, `:nitro`) or a
    casing/whitespace difference must still get the ZDR constraint, not
    silently bypass it (the exact gap the internal plan review found in the
    first draft of this policy).
    """
    return model.strip().casefold().startswith("deepseek/")


def is_glm_model(model: str) -> bool:
    """True if `model` names an OpenRouter model in the `z-ai/` namespace.

    Same normalization/namespace-matching rationale as `is_deepseek_model`.
    """
    return model.strip().casefold().startswith("z-ai/")


def resolve_extra_body(model: str) -> dict:
    """Return the OpenRouter `extra_body` for `model`, or `{}`.

    For any model outside the `deepseek/` or `z-ai/` namespaces, returns `{}`
    WITHOUT loading `shared/config/external_review.json` at all — the
    short-circuit that keeps a non-gated override immune to that config's
    health.

    For a recognized namespace, loads the config and returns the matching
    provider's `*_openrouter_extra_body(config)`. Raises
    `DeepSeekRoutingPolicyError`/`GlmRoutingPolicyError` (routing policy
    invalid) or the config loader's own exceptions (missing file, malformed
    JSON) uncaught — `pr_review.py` is the single place that maps any of
    these to the gate's fail-closed `EXIT_ERROR`, before any network call.
    """
    if is_deepseek_model(model):
        return deepseek_openrouter_extra_body(load_review_config())
    if is_glm_model(model):
        return glm_openrouter_extra_body(load_review_config())
    return {}

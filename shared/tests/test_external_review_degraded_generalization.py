"""Regression tests for generalizing ``is_degraded`` / ``is_partially_degraded``
from a hardcoded provider allowlist to a leg-status-derived check
(iterate-2026-09-03-codex-cli-review-leg).

The old shape gated on ``provider in ("openrouter", "direct")`` and could
not describe a mixed-route pass (GLM via OpenRouter, GPT via the Codex CLI).
These tests pin the exact old-vs-new equivalence for every provider
combination the old allowlist covered, plus the new mixed-route case the
old shape could not represent at all.
"""

import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from external_review_degraded import is_degraded, is_partially_degraded  # noqa: E402

_SKIP = {"status": "skipped", "reason": "no key"}
_OK = {"status": "success", "feedback": "ok"}
_ERR = {"status": "error", "reason": "boom"}


def test_openrouter_attempted_both_zero_succeed_is_degraded():
    reviews = {"glm": _ERR, "openai": _ERR}
    assert is_degraded(reviews) is True
    assert is_partially_degraded(reviews) is False


def test_openrouter_attempted_one_succeeds_is_not_degraded_but_is_partial():
    reviews = {"glm": _OK, "openai": _ERR}
    assert is_degraded(reviews) is False
    assert is_partially_degraded(reviews) is True


def test_direct_attempted_one_leg_only_zero_succeed_is_degraded():
    reviews = {"glm": _SKIP, "openai": _ERR}
    assert is_degraded(reviews) is True
    assert is_partially_degraded(reviews) is False


def test_skipped_all_no_keys_is_never_degraded():
    reviews = {"glm": _SKIP, "openai": _SKIP}
    assert is_degraded(reviews) is False
    assert is_partially_degraded(reviews) is False


def test_both_succeed_is_neither_degraded_nor_partial():
    reviews = {"glm": _OK, "openai": _OK}
    assert is_degraded(reviews) is False
    assert is_partially_degraded(reviews) is False


def test_mixed_route_pass_glm_openrouter_openai_codex_both_succeed():
    """The scenario the old provider-string allowlist could not represent at
    all: GLM answers via OpenRouter, the GPT leg answers via Codex, in the
    same pass. A single 'provider' label cannot describe this — the
    generalized check doesn't need one."""
    reviews = {"glm": _OK, "openai": {"status": "success", "feedback": "ok", "via": "codex"}}
    assert is_degraded(reviews) is False
    assert is_partially_degraded(reviews) is False


def test_mixed_route_pass_codex_leg_degrades_alone_is_partial_not_fully_degraded():
    reviews = {"glm": _OK, "openai": {"status": "degraded", "via": "codex", "reason": "empty reply"}}
    assert is_degraded(reviews) is False
    assert is_partially_degraded(reviews) is True


def test_codex_only_leg_attempted_and_fails_with_glm_skipped_is_degraded():
    reviews = {"glm": _SKIP, "openai": {"status": "error", "via": "codex", "reason": "codex exec exited 1"}}
    assert is_degraded(reviews) is True
    assert is_partially_degraded(reviews) is False

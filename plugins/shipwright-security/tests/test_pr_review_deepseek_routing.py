"""Tests for pr_review.py's ZDR routing gate in main() — split out of
test_pr_review_script.py to keep that module inside the file-size guideline
(iterate-2026-08-31-pr-review-deepseek-model). Filename kept for history;
covers both the default GLM arm (iterate-2026-09-01-pr-review-glm-model)
and the DeepSeek operator-override arm.

Covers the fail-closed contract at the resolve_extra_body() call site: a
broken routing policy or a malformed shared config must exit before any
OpenRouter call, and a non-gated model override must never touch that
config at all. All network and `gh` boundaries are monkeypatched offline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import pr_review  # noqa: E402

FAKE_KEY = "ORTESTKEY-not-a-real-credential-0123456789"
ARGV = ["--pr-number", "42", "--repo", "owner/repo", "--prompt-dir", "shared/prompts/pr_reviewer"]


def _wire(monkeypatch, *, review_json=None, diff="diff --git a b\n+x\n"):
    """Patch every external boundary; capture posted comment/review state and
    per-boundary call counts (the fail-closed tests assert these are 0)."""
    posted = {"call_openrouter_n": 0, "fetch_pr_diff_n": 0, "read_reviewed_head_n": 0}
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setattr(pr_review, "load_prompts", lambda d: ("SYSTEM", "USER\n{PR_META}\n{DIFF}"))

    def fake_fetch(pr, repo):
        posted["fetch_pr_diff_n"] += 1
        return diff

    monkeypatch.setattr(pr_review, "fetch_pr_diff", fake_fetch)

    def fake_call(api_key, model, messages, timeout=120, *, extra_body=None):
        posted["call_openrouter_n"] += 1
        posted["messages"] = messages
        posted["extra_body"] = extra_body
        return review_json

    monkeypatch.setattr(pr_review, "call_openrouter", fake_call)
    monkeypatch.setattr(
        pr_review, "post_pr_comment", lambda pr, repo, body: posted.update(comment=body))
    monkeypatch.setattr(
        pr_review, "post_pr_review_state",
        lambda pr, repo, decision, summary: posted.update(state=decision))

    def fake_head(pr, repo):
        posted["read_reviewed_head_n"] += 1
        return "headsha"

    monkeypatch.setattr(pr_review, "read_reviewed_head", fake_head)
    monkeypatch.setattr(
        pr_review, "dismiss_own_stale_verdicts",
        lambda pr, repo, *, nonce, reviewed_sha: None)
    return posted


class TestZdrRoutingGate:

    def test_the_default_luna_model_never_touches_zdr_routing(self, monkeypatch):
        # The positive case for the CURRENT default (GPT-5.6 Luna,
        # iterate-2026-09-03-pr-review-sonnet-default, after GLM 5.3 was found
        # to silently hang mid-review — see pr_review_openrouter.py's
        # DEFAULT_MODEL comment): with no override, main() must thread an
        # EMPTY extra_body through — Luna is outside the deepseek/z-ai
        # namespaces, so resolve_extra_body's short-circuit applies and no ZDR
        # provider pin (with its `allow_fallbacks: false`) is ever added.
        posted = _wire(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []}))
        assert pr_review.main(ARGV) == 0
        assert posted["extra_body"] == {}

    def test_the_deepseek_override_still_delivers_the_zdr_body(self, monkeypatch):
        # DeepSeek stays available as an operator override on the same env var
        # after the default swap — its ZDR routing must still actually work,
        # not just still exist as dead code.
        monkeypatch.setenv("SHIPWRIGHT_PR_REVIEW_MODEL", pr_review.DEEPSEEK_MODEL)
        posted = _wire(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []}))
        assert pr_review.main(ARGV) == 0
        assert posted["extra_body"]["provider"]["zdr"] is True
        assert posted["extra_body"]["provider"]["only"] == ["novita", "together"]

    def test_the_glm_override_still_delivers_the_zdr_body(self, monkeypatch):
        # GLM 5.3 stays available as an operator override too (its hang was an
        # availability problem with the shared ZDR provider pool, not a reason
        # to remove the routing wiring) — its ZDR routing must still work.
        monkeypatch.setenv("SHIPWRIGHT_PR_REVIEW_MODEL", pr_review.GLM_MODEL)
        posted = _wire(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []}))
        assert pr_review.main(ARGV) == 0
        assert posted["extra_body"]["provider"]["zdr"] is True
        assert posted["extra_body"]["provider"]["only"] == ["novita", "together"]

    def test_fails_closed_before_any_network_call_on_broken_routing(self, monkeypatch):
        # resolve_extra_body() is called for EVERY model, gated or not (see
        # DEFAULT_MODEL's own non-gated case above) — mock it directly so this
        # covers the fail-closed contract regardless of which model is
        # currently the default. A broken routing block must exit 2 WITHOUT
        # ever reaching call_openrouter OR fetching the diff/head — the AC is
        # "no OpenRouter call made, before the diff is even fetched", not just
        # the exit code.
        calls = _wire(monkeypatch)

        def boom(model):
            raise pr_review.GlmRoutingPolicyError("glm_routing is missing or not an object")
        monkeypatch.setattr(pr_review, "resolve_extra_body", boom)
        assert pr_review.main(ARGV) == 2
        assert calls["call_openrouter_n"] == 0
        assert calls["fetch_pr_diff_n"] == 0
        assert calls["read_reviewed_head_n"] == 0

    def test_fails_closed_on_malformed_external_review_json(self, monkeypatch):
        calls = _wire(monkeypatch)

        def boom(model):
            raise json.JSONDecodeError("bad json", "doc", 0)
        monkeypatch.setattr(pr_review, "resolve_extra_body", boom)
        assert pr_review.main(ARGV) == 2
        assert calls["call_openrouter_n"] == 0
        assert calls["fetch_pr_diff_n"] == 0
        assert calls["read_reviewed_head_n"] == 0

    def test_non_gated_override_never_touches_the_review_config(self, monkeypatch):
        # An operator override to a non-gated model (e.g. a Sonnet rollback)
        # must proceed exactly as it always has — no config load, no ZDR body.
        # Uses the REAL resolve_extra_body (its short-circuit is the thing
        # under test); only its config loader is stubbed to prove it's unreached.
        import pr_review_model_policy as _policy

        monkeypatch.setenv("SHIPWRIGHT_PR_REVIEW_MODEL", "anthropic/claude-sonnet-4.6")

        def boom():
            raise AssertionError("must not load the review config for a non-gated model")
        monkeypatch.setattr(_policy, "load_review_config", boom)
        posted = _wire(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []}))
        assert pr_review.main(ARGV) == 0
        assert posted["extra_body"] == {}

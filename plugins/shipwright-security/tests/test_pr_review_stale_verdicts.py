"""Tests for pr_review.main() — WHEN this reviewer may retract its own verdicts.

`pr_review_dismiss` decides *which* review is stale; this module pins the far
narrower question the orchestration owns: a run may clear its own earlier
change-requests only when it has itself just passed, and that housekeeping can
never change what the review earned. Split from `test_pr_review_script.py` to
keep both modules inside the source-size guideline.

The wiring here is deliberately its own, smaller than that module's: these tests
care about the posted review-state body and whether the cleanup ran, not about
what reached the model.
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

_PASS = json.dumps({"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []})
_BLOCK = json.dumps({"decision": "block", "summary": "no", "blocking": ["b"], "comments": []})


def _wire(monkeypatch, *, review_json=_PASS, diff="diff --git a b\n+x\n"):
    """Patch every boundary main() touches; record the review state, the ORDER
    of the two reads, and whether the stale-verdict cleanup ran. Nothing here
    reaches the network or `gh`."""
    seen = {"order": []}
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setattr(pr_review, "load_prompts", lambda d: ("SYSTEM", "USER\n{PR_META}\n{DIFF}"))
    # This suite is about the stale-verdict cleanup, not DeepSeek routing —
    # stub the resolver so it doesn't depend on the shared config's health.
    monkeypatch.setattr(pr_review, "resolve_extra_body", lambda model: {})

    def fake_diff(pr, repo):
        seen["order"].append("diff")
        return diff

    monkeypatch.setattr(pr_review, "fetch_pr_diff", fake_diff)
    monkeypatch.setattr(pr_review, "call_openrouter",
                        lambda key, model, messages, timeout=120, **kw: review_json)
    monkeypatch.setattr(pr_review, "post_pr_comment",
                        lambda pr, repo, body: seen.update(comment=body))
    monkeypatch.setattr(pr_review, "post_pr_review_state",
                        lambda pr, repo, decision, body: seen.update(state=decision, body=body))
    def fake_head(pr, repo):
        # A DIFFERENT sha on every call. Returning one constant would let
        # `cleanup_sha == reviewed_sha` pass while comparing a value against
        # itself — so a second, later head read could silently replace the
        # pre-diff one and the assertion would not notice.
        seen["order"].append("head")
        seen.setdefault("heads", []).append(f"headsha{len(seen['heads']) + 1}")
        seen["reviewed_sha"] = seen["heads"][0]
        return seen["heads"][-1]

    monkeypatch.setattr(pr_review, "read_reviewed_head", fake_head)
    monkeypatch.setattr(pr_review, "dismiss_own_stale_verdicts",
                        lambda pr, repo, *, nonce, reviewed_sha: seen.update(
                            cleanup_nonce=nonce, cleanup_sha=reviewed_sha))
    return seen


def _raise(exc):
    def _fn(*a, **k):
        raise exc
    return _fn


class TestItClearsOnlyAfterPassing:

    def test_a_passing_verdict_clears_its_own_stale_ones(self, monkeypatch):
        seen = _wire(monkeypatch)
        assert pr_review.main(ARGV) == pr_review.EXIT_OK
        assert seen.get("cleanup_nonce"), "a passing review must clear its stale verdicts"

    def test_the_cleanup_is_told_which_commit_was_actually_reviewed(self, monkeypatch):
        # A review's own `commit_id` is stamped at SUBMISSION time, so it cannot
        # answer "what did this run read?". The head captured before the diff
        # was fetched is the only thing that can, and it has to reach the
        # cleanup — otherwise its head guard proves nothing (see AC5).
        seen = _wire(monkeypatch)
        pr_review.main(ARGV)
        assert seen["cleanup_sha"] == seen["reviewed_sha"]

    def test_the_head_is_read_before_the_diff_is_fetched(self, monkeypatch):
        # THE regression guard for this whole iterate. Move the head read below
        # `fetch_pr_diff` — or down beside the cleanup call — and `reviewed_sha`
        # stops being "the commit whose diff I read" and becomes "the head just
        # now", which collapses the three-term guard back to the two terms that
        # were the original defect.
        #
        # EXACT, not a prefix slice, and the count is pinned too: `order[:2]`
        # alone survives ADDING a second read before the cleanup and passing
        # that value instead — the same collapse, reached by duplication rather
        # than by moving. One read, first, is the whole contract.
        seen = _wire(monkeypatch)
        pr_review.main(ARGV)
        assert seen["order"] == ["head", "diff"]
        assert seen["order"].count("head") == 1

    def test_the_cleanup_looks_for_the_nonce_this_run_actually_posted(self, monkeypatch):
        # The anchor is THIS invocation's review. Were the nonce handed to the
        # cleanup not the one stamped on the posted body, the cleanup would find
        # no anchor and quietly do nothing — green tests, dead feature.
        seen = _wire(monkeypatch, review_json=json.dumps(
            {"decision": "comment", "summary": "nit", "blocking": [], "comments": ["c"]}))
        pr_review.main(ARGV)
        assert f"<!-- shipwright-pr-review:{seen['cleanup_nonce']} -->" in seen["body"]

    def test_a_blocking_verdict_clears_nothing(self, monkeypatch):
        # The run that says NO must never retract a NO.
        seen = _wire(monkeypatch, review_json=_BLOCK)
        assert pr_review.main(ARGV) == pr_review.EXIT_BLOCK
        assert "cleanup_nonce" not in seen

    def test_a_truncated_diff_clears_nothing(self, monkeypatch):
        # A partial review fails closed whatever the model said — also a NO.
        big = ("diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n"
               "@@ -1 +1 @@\n" + "+z" * pr_review.MAX_DIFF_CHARS + "\n")
        seen = _wire(monkeypatch, diff=big)
        assert pr_review.main(ARGV) == pr_review.EXIT_BLOCK
        assert seen["state"] == "block"
        assert "cleanup_nonce" not in seen

    def test_an_unreviewable_diff_clears_nothing(self, monkeypatch):
        seen = _wire(monkeypatch, diff="")
        assert pr_review.main(ARGV) == pr_review.EXIT_BLOCK
        assert "cleanup_nonce" not in seen

    def test_an_unknown_decision_clears_nothing(self, monkeypatch):
        seen = _wire(monkeypatch, review_json=json.dumps({"decision": "maybe"}))
        assert pr_review.main(ARGV) == pr_review.EXIT_ERROR
        assert "cleanup_nonce" not in seen

    def test_no_cleanup_when_the_review_state_never_landed(self, monkeypatch):
        # Without a posted review there is no anchor on the pull request, so the
        # cleanup cannot identify itself. It must not fall back to the login.
        seen = _wire(monkeypatch)
        monkeypatch.setattr(pr_review, "post_pr_review_state", _raise(RuntimeError("403")))
        assert pr_review.main(ARGV) == pr_review.EXIT_OK
        assert "cleanup_nonce" not in seen


class TestItNeverMovesTheGate:

    def test_a_failing_cleanup_does_not_flip_the_gate(self, monkeypatch):
        # The verdict is already posted and the required check reflects the
        # REVIEW. Housekeeping that raises must not turn a pass into an error.
        _wire(monkeypatch)
        monkeypatch.setattr(pr_review, "dismiss_own_stale_verdicts", _raise(RuntimeError("boom")))
        assert pr_review.main(ARGV) == pr_review.EXIT_OK

    def test_a_failing_cleanup_is_reported_not_swallowed(self, monkeypatch, capsys):
        _wire(monkeypatch)
        monkeypatch.setattr(pr_review, "dismiss_own_stale_verdicts", _raise(RuntimeError("boom")))
        pr_review.main(ARGV)
        assert "boom" in capsys.readouterr().err

    def test_the_belt_and_braces_handler_redacts(self, monkeypatch, capsys):
        # `dismiss_own_stale_verdicts` is implemented never to raise, so this
        # handler is unreachable in production — it exists so a future edit that
        # breaks that promise cannot take the gate with it. Named for what it
        # is: this is NOT the path the cleanup actually prints on. That one is
        # inside pr_review_dismiss, which never sees the key (it is never given
        # to `gh`) and is pinned there for control characters instead.
        _wire(monkeypatch, review_json=json.dumps({"decision": "approve", "summary": FAKE_KEY}))
        monkeypatch.setattr(pr_review, "dismiss_own_stale_verdicts", _raise(RuntimeError(FAKE_KEY)))
        pr_review.main(ARGV)
        captured = capsys.readouterr()
        assert FAKE_KEY not in captured.err and FAKE_KEY not in captured.out

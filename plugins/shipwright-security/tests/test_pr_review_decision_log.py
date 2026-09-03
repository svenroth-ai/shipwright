"""Tests for pr_review.py's unconditional decision-log excerpt — split out of
test_pr_review_script.py to keep that module inside the file-size guideline
(iterate-2026-09-03-pr-review-block-visibility).

trg: PR #672's 4 legitimate GLM-5.3 `block` verdicts read as a silent CI hang
across 4 runs because main() printed nothing past "reviewing PR..." for a
correct block/approve/comment decision — only the unknown-decision path
explained itself. The full findings were already posted as a PR comment (see
test_pr_review_script.py::test_the_fail_closed_comment_does_not_credit_a_model
and friends); this module covers the CI-log excerpt that now says so too, via
`pr_review_verdict.finish_decision`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import pr_review  # noqa: E402

# Deliberately NOT in any real credential format so the repo's secret-scan
# hooks don't flag this synthetic fixture. Redaction is format-agnostic.
FAKE_KEY = "ORTESTKEY-not-a-real-credential-0123456789"

ARGV = ["--pr-number", "42", "--repo", "owner/repo", "--prompt-dir", "shared/prompts/pr_reviewer"]


def _wire(monkeypatch, *, review_json=None, diff="diff --git a b\n+x\n"):
    """Patch every external boundary; capture posted comment/review state."""
    posted = {}
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    monkeypatch.setattr(pr_review, "load_prompts", lambda d: ("SYSTEM", "USER\n{PR_META}\n{DIFF}"))
    monkeypatch.setattr(pr_review, "fetch_pr_diff", lambda pr, repo: diff)
    monkeypatch.setattr(pr_review, "resolve_extra_body", lambda model: {})

    def fake_call(api_key, model, messages, timeout=120, *, extra_body=None):
        posted["messages"] = messages
        posted["extra_body"] = extra_body
        return review_json

    monkeypatch.setattr(pr_review, "call_openrouter", fake_call)
    monkeypatch.setattr(
        pr_review, "post_pr_comment", lambda pr, repo, body: posted.update(comment=body))
    monkeypatch.setattr(
        pr_review, "post_pr_review_state",
        lambda pr, repo, decision, summary: posted.update(state=decision))
    monkeypatch.setattr(pr_review, "read_reviewed_head", lambda pr, repo: "headsha")
    monkeypatch.setattr(
        pr_review, "dismiss_own_stale_verdicts",
        lambda pr, repo, *, nonce, reviewed_sha: None)
    return posted


class TestDecisionLog:

    def test_block_decision_logs_a_bounded_excerpt(self, monkeypatch, capsys):
        _wire(monkeypatch, review_json=json.dumps(
            {"decision": "block", "summary": "Two real defects found in the diff.",
             "blocking": ["b"], "comments": []}))
        assert pr_review.main(ARGV) == 1
        err = capsys.readouterr().err
        assert "decision=block" in err
        assert "exit=1" in err
        assert "Two real defects found in the diff." in err
        assert "PR comment" in err

    def test_approve_and_comment_also_log_unconditionally(self, monkeypatch, capsys):
        # Not just the error path — every decision must be visible in the log,
        # so a reader never has to guess whether the gate ran at all.
        _wire(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []}))
        assert pr_review.main(ARGV) == 0
        assert "decision=approve" in capsys.readouterr().err

        _wire(monkeypatch, review_json=json.dumps(
            {"decision": "comment", "summary": "nit", "blocking": [], "comments": ["c"]}))
        assert pr_review.main(ARGV) == 0
        assert "decision=comment" in capsys.readouterr().err

    def test_decision_log_excerpt_is_bounded(self, monkeypatch, capsys):
        # A model-authored summary is untrusted-length input — the CI log line
        # must not become a second copy of an arbitrarily long comment.
        _wire(monkeypatch, review_json=json.dumps(
            {"decision": "comment", "summary": "x" * 5000, "blocking": [], "comments": []}))
        pr_review.main(ARGV)
        err = capsys.readouterr().err
        assert len(err) < 1000

    def test_decision_log_excerpt_is_redacted(self, monkeypatch, capsys):
        # Every string reaching stderr goes through `_redact` (pr_review_lib
        # docstring) — the new line is no exception, even though a model
        # summary carrying the key is a synthetic/adversarial case.
        _wire(monkeypatch, review_json=json.dumps(
            {"decision": "block", "summary": f"leaked {FAKE_KEY} in summary",
             "blocking": [], "comments": []}))
        pr_review.main(ARGV)
        assert FAKE_KEY not in capsys.readouterr().err

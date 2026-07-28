"""Tests for scripts/lib/pr_review_gh.py — the `gh`-CLI boundary.

This is where attacker-controlled bytes enter the process, so the contract that
matters most is the one the fetch does NOT have: no newline translation. Split
out of test_pr_review_script.py alongside the module itself
(iterate-2026-07-27-pr-review-forged-boundary).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_gh as G  # noqa: E402


class _Proc:
    """Fake CompletedProcess. `gh pr diff` is read as BYTES; the others as text."""

    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class TestFetchPrDiff:

    def test_success_decodes_utf8(self, monkeypatch):
        monkeypatch.setattr(G.subprocess, "run",
                            lambda *a, **k: _Proc(0, "DIFFTEXT äöü".encode()))
        assert G.fetch_pr_diff(1, "o/r") == "DIFFTEXT äöü"

    def test_failure_raises(self, monkeypatch):
        monkeypatch.setattr(G.subprocess, "run",
                            lambda *a, **k: _Proc(1, b"", b"no auth"))
        with pytest.raises(RuntimeError, match="no auth"):
            G.fetch_pr_diff(1, "o/r")

    def test_it_does_not_ask_for_text_mode(self, monkeypatch):
        # `text=True` would run CPython's universal-newline pass and rewrite a
        # lone CR to LF before any parser sees it — which is how a PR forges a
        # `diff --git` boundary from inside a hunk. Pin the absence.
        seen = {}

        def fake_run(cmd, **kw):
            seen.update(kw)
            return _Proc(0, b"")

        monkeypatch.setattr(G.subprocess, "run", fake_run)
        G.fetch_pr_diff(1, "o/r")
        assert seen.get("text") is not True
        assert "universal_newlines" not in seen
        # `encoding=` and `errors=` ALSO put subprocess in text mode with
        # newline=None — i.e. the same universal-newline translation, reached by
        # a different kwarg. The sibling calls in this module define exactly
        # such a `_TEXT` dict eleven lines below, so spreading it in here "for
        # consistency" is the realistic regression, and `text` alone would not
        # catch it.
        assert "encoding" not in seen and "errors" not in seen

    def test_a_lone_cr_survives_the_fetch(self, monkeypatch):
        # The regression this module exists for: git ends a line at LF only, so
        # a CR inside a diff line must still be a CR when the parser gets it.
        raw = b'+BANNER = "x\rdiff --git a/.shipwright/compliance/x.md b/x.md"\n'
        monkeypatch.setattr(G.subprocess, "run", lambda *a, **k: _Proc(0, raw))
        out = G.fetch_pr_diff(1, "o/r")
        assert "\r" in out
        assert not any(ln.startswith("diff --git ") for ln in out.split("\n"))

    def test_undecodable_bytes_do_not_crash_the_gate(self, monkeypatch):
        monkeypatch.setattr(G.subprocess, "run", lambda *a, **k: _Proc(0, b"\xff\xfe ok"))
        assert "ok" in G.fetch_pr_diff(1, "o/r")


class TestPostComment:

    def test_failure_raises(self, monkeypatch):
        monkeypatch.setattr(G.subprocess, "run", lambda *a, **k: _Proc(1, "", "forbidden"))
        with pytest.raises(RuntimeError):
            G.post_pr_comment(1, "o/r", "body")

    def test_the_body_is_encoded_as_utf8_not_by_locale(self, monkeypatch):
        # The rendered comment ALWAYS carries non-ASCII (the decision badges).
        # `text=True` encodes with locale.getpreferredencoding(False), so a
        # runner whose LC_CTYPE is not UTF-8 raises here, the caller swallows it
        # best-effort, and the maintainer gets a red required check with no
        # comment explaining it.
        seen = {}
        monkeypatch.setattr(G.subprocess, "run",
                            lambda cmd, **k: (seen.update(k), _Proc(0))[1])
        G.post_pr_comment(1, "o/r", "## 🤖 review")
        assert seen.get("encoding") == "utf-8"
        assert seen.get("errors") == "replace"
        assert "text" not in seen


class TestReviewState:

    def test_block_requests_changes(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(G.subprocess, "run",
                            lambda cmd, **k: (captured.update(cmd=cmd), _Proc(0))[1])
        G.post_pr_review_state(1, "o/r", "block", "nope")
        assert "--request-changes" in captured["cmd"]

    def test_non_block_comments_with_a_non_empty_body(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(G.subprocess, "run",
                            lambda cmd, **k: (captured.update(cmd=cmd), _Proc(0))[1])
        G.post_pr_review_state(1, "o/r", "approve", "")
        assert "--comment" in captured["cmd"]
        assert "--body" in captured["cmd"]

    def test_a_failure_is_raised_rather_than_discarded(self, monkeypatch):
        # Best-effort means the GATE does not flip on a posting failure — not
        # that the failure goes unrecorded. `gh pr review` fails on a rate
        # limit, a revoked token, or "can not review your own pull request";
        # discarding the CompletedProcess left the caller's except clause dead.
        monkeypatch.setattr(G.subprocess, "run",
                            lambda *a, **k: _Proc(1, "", "rate limited"))
        with pytest.raises(RuntimeError, match="rate limited"):
            G.post_pr_review_state(1, "o/r", "block", "nope")

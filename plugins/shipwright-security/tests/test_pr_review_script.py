"""Tests for scripts/tools/pr_review.py — the Tier-3 PR reviewer (I/O + orchestration).

The script is the OpenRouter-backed reviewer invoked by `.github/workflows/pr-review.yml`
for Tier-3 PRs (external contributors, sensitive paths, or `needs-review` label). It must:

- fetch the PR diff, call OpenRouter, parse a strict-JSON decision, post a PR comment
- map the decision to an exit code: 0 = approve/comment, 1 = block, 2 = error
- dump the raw response (redacted) on a JSON-parse failure and exit 2
- truncate a > 200k-char diff and NOT auto-block on a (partial) truncated review
- never write the OpenRouter API key to logs

The pure helpers (parse/truncate/render/redact/decision-mapping) live in
pr_review_lib.py and are covered by test_pr_review_lib.py. All network (`urllib`)
and `gh`-subprocess boundaries are monkeypatched so the suite runs fully offline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import pr_review  # noqa: E402

# Deliberately NOT in any real credential format (no `sk-`/`ghp_`/`xox` prefix) so the
# repo's secret-scan hooks don't flag this synthetic fixture. Redaction is format-agnostic.
FAKE_KEY = "ORTESTKEY-not-a-real-credential-0123456789"


# ---------------------------------------------------------------------------
# File contract
# ---------------------------------------------------------------------------

class TestFileContract:

    def test_script_exists(self):
        assert (PLUGIN_ROOT / "scripts" / "tools" / "pr_review.py").exists()

    def test_shebang_present(self):
        first = (PLUGIN_ROOT / "scripts" / "tools" / "pr_review.py").read_text(
            encoding="utf-8"
        ).splitlines()[0]
        assert first == "#!/usr/bin/env python3", "missing python3 shebang"

    def test_uses_openrouter_key_not_anthropic(self):
        src = (PLUGIN_ROOT / "scripts" / "tools" / "pr_review.py").read_text(encoding="utf-8")
        assert "OPENROUTER_API_KEY" in src, "script must read OPENROUTER_API_KEY"
        assert "ANTHROPIC_API_KEY" not in src, (
            "script must not reference ANTHROPIC_API_KEY — OpenRouter is the single provider"
        )

    def test_default_model_is_sonnet(self):
        assert pr_review.DEFAULT_MODEL == "anthropic/claude-sonnet-4.6"


# ---------------------------------------------------------------------------
# _post_openrouter — HTTP boundary (urllib monkeypatched)
# ---------------------------------------------------------------------------

class TestPostOpenRouter:

    def test_builds_authorized_json_request(self, monkeypatch):
        captured = {}

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "{\"decision\":\"approve\"}"}}]}
                ).encode("utf-8")

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = {k.lower(): v for k, v in req.header_items()}
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeResp()

        monkeypatch.setattr(pr_review.urllib.request, "urlopen", fake_urlopen)
        data = pr_review._post_openrouter(FAKE_KEY, "some/model", [{"role": "user", "content": "hi"}], 30)

        assert captured["url"] == pr_review.OPENROUTER_URL
        assert captured["headers"]["authorization"] == f"Bearer {FAKE_KEY}"
        assert captured["body"]["model"] == "some/model"
        assert captured["body"]["response_format"] == {"type": "json_object"}
        assert data["choices"][0]["message"]["content"] == '{"decision":"approve"}'


# ---------------------------------------------------------------------------
# call_openrouter — content extraction + error wrapping (_post_openrouter mocked)
# ---------------------------------------------------------------------------

class TestCallOpenRouter:

    def test_success_extracts_content(self, monkeypatch):
        monkeypatch.setattr(
            pr_review, "_post_openrouter",
            lambda k, m, msgs, t: {"choices": [{"message": {"content": "OK"}}]},
        )
        assert pr_review.call_openrouter("k", "m", [], 1) == "OK"

    def test_bad_shape_raises_runtime(self, monkeypatch):
        monkeypatch.setattr(pr_review, "_post_openrouter", lambda *a: {"unexpected": 1})
        with pytest.raises(RuntimeError):
            pr_review.call_openrouter("k", "m", [], 1)

    def test_http_error_wrapped(self, monkeypatch):
        def boom(*a):
            raise pr_review.urllib.error.HTTPError("u", 429, "rate limit", {}, None)
        monkeypatch.setattr(pr_review, "_post_openrouter", boom)
        with pytest.raises(RuntimeError):
            pr_review.call_openrouter("k", "m", [], 1)

    def test_url_error_wrapped(self, monkeypatch):
        def boom(*a):
            raise pr_review.urllib.error.URLError("connection refused")
        monkeypatch.setattr(pr_review, "_post_openrouter", boom)
        with pytest.raises(RuntimeError):
            pr_review.call_openrouter("k", "m", [], 1)


# ---------------------------------------------------------------------------
# gh-CLI wrappers — exit handling (subprocess mocked)
# ---------------------------------------------------------------------------

class _Proc:
    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class TestGhWrappers:

    def test_fetch_pr_diff_success(self, monkeypatch):
        monkeypatch.setattr(pr_review.subprocess, "run", lambda *a, **k: _Proc(0, "DIFFTEXT"))
        assert pr_review.fetch_pr_diff(1, "o/r") == "DIFFTEXT"

    def test_fetch_pr_diff_failure_raises(self, monkeypatch):
        monkeypatch.setattr(pr_review.subprocess, "run", lambda *a, **k: _Proc(1, "", "no auth"))
        with pytest.raises(RuntimeError):
            pr_review.fetch_pr_diff(1, "o/r")

    def test_post_pr_comment_failure_raises(self, monkeypatch):
        monkeypatch.setattr(pr_review.subprocess, "run", lambda *a, **k: _Proc(1, "", "forbidden"))
        with pytest.raises(RuntimeError):
            pr_review.post_pr_comment(1, "o/r", "body")

    def test_review_state_block_requests_changes(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **k):
            captured["cmd"] = cmd
            return _Proc(0)

        monkeypatch.setattr(pr_review.subprocess, "run", fake_run)
        pr_review.post_pr_review_state(1, "o/r", "block", "nope")
        assert "--request-changes" in captured["cmd"]

    def test_review_state_non_block_comments(self, monkeypatch):
        captured = {}

        def fake_run(cmd, **k):
            captured["cmd"] = cmd
            return _Proc(0)

        monkeypatch.setattr(pr_review.subprocess, "run", fake_run)
        pr_review.post_pr_review_state(1, "o/r", "approve", "")
        assert "--comment" in captured["cmd"]
        # empty summary must still pass a non-empty body to `gh pr review`
        assert "--body" in captured["cmd"]


# ---------------------------------------------------------------------------
# main() orchestration — boundaries monkeypatched
# ---------------------------------------------------------------------------

def _wire(monkeypatch, *, review_json=None, diff="diff --git a b\n+x\n", raise_call=None):
    """Patch every external boundary; capture posted comment/review state."""
    posted = {}
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    # Isolate orchestration from the filesystem prompt files (cwd-dependent).
    monkeypatch.setattr(pr_review, "load_prompts", lambda d: ("SYSTEM", "USER\n{PR_META}\n{DIFF}"))
    monkeypatch.setattr(pr_review, "fetch_pr_diff", lambda pr, repo: diff)

    def fake_call(api_key, model, messages, timeout=120):
        if raise_call is not None:
            raise raise_call
        return review_json

    monkeypatch.setattr(pr_review, "call_openrouter", fake_call)
    monkeypatch.setattr(
        pr_review, "post_pr_comment",
        lambda pr, repo, body: posted.update(comment=body),
    )
    monkeypatch.setattr(
        pr_review, "post_pr_review_state",
        lambda pr, repo, decision, summary: posted.update(state=decision),
    )
    return posted


ARGV = ["--pr-number", "42", "--repo", "owner/repo", "--prompt-dir", "shared/prompts/pr_reviewer"]


class TestMainOrchestration:

    def test_missing_api_key_exits_2(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        assert pr_review.main(ARGV) == 2

    def test_block_exits_1(self, monkeypatch):
        _wire(monkeypatch, review_json=json.dumps(
            {"decision": "block", "summary": "no", "blocking": ["b"], "comments": []}))
        assert pr_review.main(ARGV) == 1

    def test_approve_exits_0(self, monkeypatch):
        posted = _wire(monkeypatch, review_json=json.dumps(
            {"decision": "approve", "summary": "lgtm", "blocking": [], "comments": []}))
        assert pr_review.main(ARGV) == 0
        assert "lgtm" in posted["comment"]

    def test_comment_exits_0(self, monkeypatch):
        _wire(monkeypatch, review_json=json.dumps(
            {"decision": "comment", "summary": "nit", "blocking": [], "comments": ["c"]}))
        assert pr_review.main(ARGV) == 0

    def test_openrouter_error_exits_2(self, monkeypatch):
        _wire(monkeypatch, raise_call=RuntimeError("502 Bad Gateway"))
        assert pr_review.main(ARGV) == 2

    def test_json_parse_fail_exits_2_and_dumps_raw(self, monkeypatch, capsys):
        _wire(monkeypatch, review_json="<html>rate limited</html>")
        assert pr_review.main(ARGV) == 2
        err = capsys.readouterr().err
        assert "rate limited" in err  # raw response dumped to logs

    def test_truncation_forces_exit_0_even_on_block(self, monkeypatch):
        # A truncated (partial) review must not auto-block: comment-state + exit 0.
        posted = _wire(
            monkeypatch,
            diff="z" * (pr_review.MAX_DIFF_CHARS + 1000),
            review_json=json.dumps(
                {"decision": "block", "summary": "huge", "blocking": ["x"], "comments": []}),
        )
        assert pr_review.main(ARGV) == 0
        assert "truncat" in posted["comment"].lower()

    def test_api_key_never_logged(self, monkeypatch, capsys):
        # Force the worst path (error message embeds the key) and assert it is
        # never present in any captured output.
        _wire(monkeypatch, raise_call=RuntimeError(f"boom with {FAKE_KEY} in message"))
        pr_review.main(ARGV)
        captured = capsys.readouterr()
        assert FAKE_KEY not in captured.out
        assert FAKE_KEY not in captured.err

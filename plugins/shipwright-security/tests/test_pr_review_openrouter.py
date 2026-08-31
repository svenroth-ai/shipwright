"""Tests for scripts/lib/pr_review_openrouter.py — the HTTP boundary.

Request shape (URL, auth header, strict-JSON response format), content
extraction, and the error wrapping that maps every transport failure to a
RuntimeError the caller turns into EXIT_ERROR. `urllib` is monkeypatched, so
the suite runs fully offline.

Split out of test_pr_review_script.py alongside the source split
(iterate-2026-07-27-pr-review-forged-boundary).
"""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_openrouter as O  # noqa: E402

# Deliberately NOT in any real credential format (no `sk-`/`ghp_`/`xox` prefix) so the
# repo's secret-scan hooks don't flag this synthetic fixture.
FAKE_KEY = "ORTESTKEY-not-a-real-credential-0123456789"


class TestDefaults:

    def test_default_model_is_deepseek(self):
        assert O.DEFAULT_MODEL == O.DEEPSEEK_MODEL == "deepseek/deepseek-v4-pro"

    def test_the_timeout_default_is_shared_with_the_cli(self):
        # Two defaults for one knob is how a raise gets half-applied. The CLI
        # flag reads this constant; nothing hardcodes a second number.
        assert O.DEFAULT_TIMEOUT == 600
        src = (PLUGIN_ROOT / "scripts" / "tools" / "pr_review.py").read_text(encoding="utf-8")
        assert "default=DEFAULT_TIMEOUT" in src

    def test_the_endpoint_is_a_fixed_https_constant(self):
        # No dynamic input may reach the request URL (the SSRF/`file://` class).
        assert O.OPENROUTER_URL.startswith("https://openrouter.ai/")


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
            captured["timeout"] = timeout
            return _FakeResp()

        monkeypatch.setattr(O.urllib.request, "urlopen", fake_urlopen)
        data = O._post_openrouter(FAKE_KEY, "some/model", [{"role": "user", "content": "hi"}], 30)

        assert captured["url"] == O.OPENROUTER_URL
        assert captured["headers"]["authorization"] == f"Bearer {FAKE_KEY}"
        assert captured["body"]["model"] == "some/model"
        assert captured["body"]["response_format"] == {"type": "json_object"}
        assert captured["timeout"] == 30
        assert data["choices"][0]["message"]["content"] == '{"decision":"approve"}'
        # No extra_body passed: payload shape is byte-identical to before this
        # change (AC — a non-DeepSeek/no-extra_body call must not regress).
        assert set(captured["body"]) == {"model", "messages", "response_format"}

    def test_merges_extra_body_defensively(self, monkeypatch):
        captured = {}

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode("utf-8")

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeResp()

        monkeypatch.setattr(O.urllib.request, "urlopen", fake_urlopen)
        # A hostile extra_body tries to overwrite the transport's own keys —
        # they must always win (`{**extra_body, **payload}`, never the reverse).
        hostile = {"provider": {"only": ["novita"]}, "model": "attacker/model",
                   "messages": [{"role": "user", "content": "attacker"}]}
        O._post_openrouter(FAKE_KEY, "real/model", [{"role": "user", "content": "hi"}], 30,
                           extra_body=hostile)

        assert captured["body"]["model"] == "real/model"
        assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]
        assert captured["body"]["response_format"] == {"type": "json_object"}
        assert captured["body"]["provider"] == {"only": ["novita"]}


class TestCallOpenRouter:

    def test_success_extracts_content(self, monkeypatch):
        monkeypatch.setattr(
            O, "_post_openrouter",
            lambda k, m, msgs, t, **kw: {"choices": [{"message": {"content": "OK"}}]},
        )
        assert O.call_openrouter("k", "m", [], 1) == "OK"

    def test_the_default_timeout_is_passed_through(self, monkeypatch):
        seen = {}

        def capture(k, m, msgs, t, **kw):
            seen["timeout"] = t
            return {"choices": [{"message": {"content": "OK"}}]}

        monkeypatch.setattr(O, "_post_openrouter", capture)
        O.call_openrouter("k", "m", [])
        assert seen["timeout"] == O.DEFAULT_TIMEOUT

    def test_bad_shape_raises_runtime(self, monkeypatch):
        monkeypatch.setattr(O, "_post_openrouter", lambda *a, **kw: {"unexpected": 1})
        with pytest.raises(RuntimeError):
            O.call_openrouter("k", "m", [], 1)

    def test_http_error_wrapped(self, monkeypatch):
        def boom(*a, **kw):
            raise urllib.error.HTTPError("u", 429, "rate limit", {}, None)
        monkeypatch.setattr(O, "_post_openrouter", boom)
        with pytest.raises(RuntimeError):
            O.call_openrouter("k", "m", [], 1)

    def test_url_error_wrapped(self, monkeypatch):
        def boom(*a, **kw):
            raise urllib.error.URLError("connection refused")
        monkeypatch.setattr(O, "_post_openrouter", boom)
        with pytest.raises(RuntimeError):
            O.call_openrouter("k", "m", [], 1)

    def test_extra_body_is_passed_through(self, monkeypatch):
        seen = {}

        def capture(k, m, msgs, t, *, extra_body=None):
            seen["extra_body"] = extra_body
            return {"choices": [{"message": {"content": "OK"}}]}

        monkeypatch.setattr(O, "_post_openrouter", capture)
        body = {"provider": {"only": ["novita"]}}
        O.call_openrouter("k", "m", [], 1, extra_body=body)
        assert seen["extra_body"] == body

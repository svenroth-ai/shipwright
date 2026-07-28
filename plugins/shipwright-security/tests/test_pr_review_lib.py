"""Tests for scripts/lib/pr_review_lib.py — the pure (I/O-free) PR-review helpers.

Redaction, prompt loading, diff truncation, strict-JSON parsing and the
decision → exit-code mapping. Siblings, each mirroring one source module:
rendering in test_pr_review_render.py, generated-artifact filtering in
test_pr_review_filter.py, the forged-boundary attack surface in
test_pr_review_forged_boundary.py, the shipped prompt template in
test_pr_review_prompt_template.py, the `gh` boundary in test_pr_review_gh.py,
and the tool-side I/O + orchestration in test_pr_review_script.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_lib as L  # noqa: E402

# Deliberately NOT in any real credential format (no `sk-`/`ghp_`/`xox` prefix) so the
# repo's secret-scan hooks don't flag this synthetic fixture. Redaction is format-agnostic.
FAKE_KEY = "ORTESTKEY-not-a-real-credential-0123456789"


class TestRedaction:

    def test_redact_masks_secret(self):
        out = L._redact(f"Authorization: Bearer {FAKE_KEY} done", FAKE_KEY)
        assert FAKE_KEY not in out
        assert "REDACTED" in out

    def test_redact_handles_none_secret(self):
        assert L._redact("hello", None) == "hello"
        assert L._redact("hello", "") == "hello"

    def test_redact_multiple_secrets(self):
        second = "SECONDFAKE-token-value-abc"
        out = L._redact(f"{FAKE_KEY} and {second}", FAKE_KEY, second)
        assert FAKE_KEY not in out
        assert second not in out


class TestDecisionToExit:

    def test_approve_is_zero(self):
        assert L.decision_to_exit("approve") == L.EXIT_OK == 0

    def test_comment_is_zero(self):
        assert L.decision_to_exit("comment") == 0

    def test_block_is_one(self):
        assert L.decision_to_exit("block") == L.EXIT_BLOCK == 1

    def test_unknown_decision_is_error(self):
        assert L.decision_to_exit("definitely-not-a-decision") == L.EXIT_ERROR == 2

    def test_case_insensitive(self):
        assert L.decision_to_exit("BLOCK") == 1
        assert L.decision_to_exit("Approve") == 0

    def test_non_string_decision_is_error_not_crash(self):
        # A model returning a non-string decision must map to exit 2, not raise.
        assert L.decision_to_exit(["block"]) == 2
        assert L.decision_to_exit(None) == 2


class TestParseResponse:

    def test_valid_json(self):
        raw = json.dumps({"decision": "block", "summary": "bad", "blocking": ["x"], "comments": []})
        review = L.parse_review_response(raw)
        assert review["decision"] == "block"
        assert review["blocking"] == ["x"]

    def test_json_object_in_markdown_fence(self):
        # OpenRouter -> Anthropic ignores response_format and fences the JSON.
        # Verified live on a B4.5 Tier-3 smoke test (exit 2 instead of the real decision).
        obj = {"decision": "block", "summary": "s", "blocking": ["b"], "comments": []}
        raw = "```json\n" + json.dumps(obj, indent=2) + "\n```"
        review = L.parse_review_response(raw)
        assert review["decision"] == "block"
        assert review["blocking"] == ["b"]

    def test_json_object_in_bare_fence(self):
        raw = "```\n" + json.dumps({"decision": "approve", "summary": "ok"}) + "\n```"
        assert L.parse_review_response(raw)["decision"] == "approve"

    def test_json_object_with_surrounding_prose(self):
        raw = 'Here is my review:\n{"decision": "comment", "summary": "nit"}\nThanks!'
        assert L.parse_review_response(raw)["decision"] == "comment"

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError):
            L.parse_review_response("this is not json")

    def test_missing_decision_raises(self):
        with pytest.raises(ValueError):
            L.parse_review_response(json.dumps({"summary": "no decision"}))

    def test_non_object_raises(self):
        with pytest.raises(ValueError):
            L.parse_review_response(json.dumps(["a", "list"]))


class TestTruncation:

    def test_short_diff_unchanged(self):
        diff = "diff --git a b\n+small change\n"
        out = L.truncate_diff(diff)
        assert out.text == diff
        assert out.incomplete is False

    def test_over_limit_truncates(self):
        diff = "x" * (L.MAX_DIFF_CHARS + 5000)
        out = L.truncate_diff(diff)
        assert out.incomplete is True
        assert len(out.text) <= L.MAX_DIFF_CHARS

    def test_exactly_at_limit_not_truncated(self):
        diff = "x" * L.MAX_DIFF_CHARS
        assert L.truncate_diff(diff).incomplete is False

    def test_the_record_cannot_be_unpacked_like_the_old_tuple(self):
        # The contract changed from a 2-tuple to a record. A stale call site
        # must fail loudly, never bind `truncated` to the wrong element.
        with pytest.raises(TypeError):
            _a, _b = L.truncate_diff("diff --git a b\n+x\n")


class TestPromptLoadingAndMessages:

    def test_load_prompts_reads_both_files(self, tmp_path):
        (tmp_path / "system").write_text("SYS-PROMPT", encoding="utf-8")
        (tmp_path / "user").write_text("USER {PR_META} {DIFF}", encoding="utf-8")
        system, user = L.load_prompts(str(tmp_path))
        assert system == "SYS-PROMPT"
        assert "{DIFF}" in user and "{PR_META}" in user

    def test_load_prompts_missing_raises(self, tmp_path):
        with pytest.raises(OSError):
            L.load_prompts(str(tmp_path))  # no system/user files

    def test_build_messages_fills_placeholders(self):
        msgs = L.build_messages("SYS", "U {PR_META} :: {DIFF}", "DD", "MM")
        assert msgs[0] == {"role": "system", "content": "SYS"}
        assert "MM" in msgs[1]["content"] and "DD" in msgs[1]["content"]

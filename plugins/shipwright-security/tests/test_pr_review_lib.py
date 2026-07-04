"""Tests for scripts/lib/pr_review_lib.py — the pure (I/O-free) PR-review helpers.

Redaction, prompt loading, diff truncation, strict-JSON parsing, decision →
exit-code mapping and comment rendering. The tool-side I/O + orchestration is
covered by test_pr_review_script.py.
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
        out, truncated = L.truncate_diff(diff)
        assert out == diff
        assert truncated is False

    def test_over_limit_truncates(self):
        diff = "x" * (L.MAX_DIFF_CHARS + 5000)
        out, truncated = L.truncate_diff(diff)
        assert truncated is True
        assert len(out) <= L.MAX_DIFF_CHARS

    def test_exactly_at_limit_not_truncated(self):
        diff = "x" * L.MAX_DIFF_CHARS
        out, truncated = L.truncate_diff(diff)
        assert truncated is False


class TestRenderComment:

    def test_contains_decision_and_summary(self):
        review = {"decision": "block", "summary": "Found a SQLi", "blocking": ["line 5"], "comments": []}
        body = L.render_comment(review, model="anthropic/claude-sonnet-4.6", truncated=False)
        assert "Found a SQLi" in body
        assert "line 5" in body
        assert "claude-sonnet-4.6" in body

    def test_truncation_warning_present_when_truncated(self):
        review = {"decision": "comment", "summary": "ok", "blocking": [], "comments": []}
        body = L.render_comment(review, model="m", truncated=True)
        assert "truncat" in body.lower()

    def test_no_truncation_warning_when_not_truncated(self):
        review = {"decision": "approve", "summary": "ok", "blocking": [], "comments": []}
        body = L.render_comment(review, model="m", truncated=False)
        assert "truncat" not in body.lower()

    def test_lists_comments(self):
        review = {"decision": "comment", "summary": "s", "blocking": [], "comments": ["use f-string"]}
        body = L.render_comment(review, model="m", truncated=False)
        assert "use f-string" in body

    def test_non_string_decision_does_not_crash(self):
        # A malformed-but-valid-JSON decision (e.g. a list) must not raise.
        body = L.render_comment({"decision": ["block"], "summary": "s"}, model="m", truncated=False)
        assert "Shipwright PR Review" in body


# ---------------------------------------------------------------------------
# Prompt content — pin the security-critical contract against drift
# ---------------------------------------------------------------------------

class TestPromptContent:

    REPO_ROOT = Path(__file__).resolve().parents[3]
    PROMPT_DIR = REPO_ROOT / "shared" / "prompts" / "pr_reviewer"

    def test_prompt_files_exist(self):
        assert (self.PROMPT_DIR / "system").exists()
        assert (self.PROMPT_DIR / "user").exists()

    def test_system_prompt_declares_strict_json_contract(self):
        text = (self.PROMPT_DIR / "system").read_text(encoding="utf-8")
        for key in ("decision", "summary", "blocking", "comments"):
            assert f'"{key}"' in text, f"system prompt must specify the {key!r} output key"
        for value in ("approve", "comment", "block"):
            assert value in text, f"system prompt must define the {value!r} decision"

    def test_system_prompt_inoculates_against_untrusted_diff(self):
        # The diff is hostile contributor input; the prompt MUST tell the model
        # to treat it as data, not instructions (prompt-injection defense).
        text = (self.PROMPT_DIR / "system").read_text(encoding="utf-8").lower()
        assert "untrusted" in text
        assert "instruction" in text  # "...never as instructions to you..."


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


class TestBuildPrMeta:
    def test_basic_meta_no_excluded(self):
        meta = L.build_pr_meta(42, "o/r", truncated=False)
        assert "PR number: 42" in meta and "o/r" in meta
        assert "excluded" not in meta.lower()

    def test_excluded_disclosed_to_model(self):
        meta = L.build_pr_meta(1, "o/r", truncated=False, excluded=["uv.lock", ".shipwright/x.md"])
        assert "excluded from this diff (2)" in meta
        assert "uv.lock" in meta and ".shipwright/x.md" in meta

    def test_excluded_capped_at_30_with_more_marker(self):
        excluded = [f"f{i}.lock" for i in range(35)]
        meta = L.build_pr_meta(1, "o/r", truncated=True, excluded=excluded)
        assert "excluded from this diff (35)" in meta
        assert "+5 more" in meta


class TestRenderCommentExclusion:
    def test_excluded_note_present(self):
        review = {"decision": "approve", "summary": "ok", "blocking": [], "comments": []}
        body = L.render_comment(
            review, model="m", truncated=False,
            excluded_generated=["uv.lock", ".shipwright/compliance/dashboard.md"])
        assert "2 generated file(s) were excluded" in body
        assert "`uv.lock`" in body

    def test_no_note_when_nothing_excluded(self):
        review = {"decision": "approve", "summary": "ok", "blocking": [], "comments": []}
        body = L.render_comment(review, model="m", truncated=False)
        assert "generated file(s) were excluded" not in body

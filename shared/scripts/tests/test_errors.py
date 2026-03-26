"""Tests for shared.scripts.lib.errors module."""

import pytest

from shared.scripts.lib.errors import (
    ERROR_CATEGORIES,
    hook_block,
    hook_error,
    structured_error,
    structured_success,
)


class TestStructuredError:
    def test_basic_error(self):
        result = structured_error(
            what_failed="Parse transcript",
            what_was_attempted="Reading JSONL from /tmp/t.jsonl",
            error_category="validation",
            is_retryable=False,
        )
        assert result["success"] is False
        err = result["error"]
        assert err["what_failed"] == "Parse transcript"
        assert err["what_was_attempted"] == "Reading JSONL from /tmp/t.jsonl"
        assert err["error_category"] == "validation"
        assert err["is_retryable"] is False
        assert err["partial_results"] == {}
        assert err["alternatives"] == []
        assert err["context"] == {}

    def test_with_partial_results_and_alternatives(self):
        result = structured_error(
            what_failed="Read transcript",
            what_was_attempted="Reading JSONL",
            error_category="transient",
            is_retryable=True,
            partial_results={"path": "/tmp/t.jsonl", "file_existed": True},
            alternatives=["Re-run subagent", "Write manually"],
        )
        err = result["error"]
        assert err["partial_results"]["file_existed"] is True
        assert len(err["alternatives"]) == 2
        assert err["is_retryable"] is True

    def test_with_context(self):
        result = structured_error(
            what_failed="Git command",
            what_was_attempted="git log",
            error_category="transient",
            is_retryable=True,
            context={"exit_code": 128, "stderr": "not a git repo"},
        )
        assert result["error"]["context"]["exit_code"] == 128

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError, match="Invalid error_category"):
            structured_error(
                what_failed="x",
                what_was_attempted="y",
                error_category="unknown",
                is_retryable=False,
            )

    def test_all_categories_accepted(self):
        for cat in ERROR_CATEGORIES:
            result = structured_error(
                what_failed="x",
                what_was_attempted="y",
                error_category=cat,
                is_retryable=False,
            )
            assert result["error"]["error_category"] == cat


class TestStructuredSuccess:
    def test_basic_success(self):
        result = structured_success()
        assert result == {"success": True}

    def test_success_with_data(self):
        result = structured_success(data={"section": "01-auth", "path": "/tmp/s.md"})
        assert result["success"] is True
        assert result["section"] == "01-auth"
        assert result["path"] == "/tmp/s.md"


class TestHookError:
    def test_basic_hook_error(self):
        result = hook_error(
            hook_event="SubagentStop",
            what_failed="Read transcript",
            what_was_attempted="Parsing JSONL",
            error_category="transient",
            is_retryable=True,
        )
        output = result["hookSpecificOutput"]
        assert output["hookEventName"] == "SubagentStop"
        assert "ERROR [transient]" in output["additionalContext"]
        assert "Read transcript" in output["additionalContext"]
        se = output["structuredError"]
        assert se["is_retryable"] is True

    def test_hook_error_with_alternatives(self):
        result = hook_error(
            hook_event="SubagentStop",
            what_failed="Extract section",
            what_was_attempted="Parsing transcript",
            error_category="validation",
            is_retryable=False,
            alternatives=["Re-run subagent"],
        )
        ctx = result["hookSpecificOutput"]["additionalContext"]
        assert "Alternatives: Re-run subagent" in ctx

    def test_hook_error_invalid_category(self):
        with pytest.raises(ValueError, match="Invalid error_category"):
            hook_error(
                hook_event="SubagentStop",
                what_failed="x",
                what_was_attempted="y",
                error_category="invalid",
                is_retryable=False,
            )


class TestHookBlock:
    def test_basic_block(self):
        result = hook_block(
            hook_event="PreToolUse",
            reason="RTM coverage 62% < 80% threshold",
            details={"coverage": 0.62, "threshold": 0.80, "missing": ["REQ-007"]},
            override_instruction="Log override to agent_docs/compliance_overrides.log",
            resume_note="Coverage gap will be flagged again at next compliance checkpoint.",
        )
        output = result["hookSpecificOutput"]
        assert output["hookEventName"] == "PreToolUse"
        assert output["blocked"] is True
        assert output["reason"] == "RTM coverage 62% < 80% threshold"
        assert output["details"]["coverage"] == 0.62
        assert "Continue anyway" in output["additionalContext"]
        assert "Log override" in output["additionalContext"]

    def test_block_has_resume_note(self):
        result = hook_block(
            hook_event="PreToolUse",
            reason="Critical findings unresolved",
            details={"findings": 2},
            override_instruction="Log override",
            resume_note="Will re-check before production deploy.",
        )
        assert "Will re-check" in result["hookSpecificOutput"]["additionalContext"]

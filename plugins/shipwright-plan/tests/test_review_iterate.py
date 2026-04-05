"""Integration tests for review.py --mode iterate."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts to path
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "llm_clients"),
)
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts"),
)


class TestReviewIterateMode:
    """Test that --mode iterate loads correct prompts and handles gracefully."""

    @pytest.fixture
    def plugin_root(self):
        return str(Path(__file__).resolve().parent.parent)

    def test_iterate_prompts_exist(self, plugin_root):
        """Iterate reviewer prompt files should exist."""
        prompts_dir = Path(plugin_root) / "prompts" / "iterate_reviewer"
        assert (prompts_dir / "system").exists(), "iterate_reviewer/system prompt missing"
        assert (prompts_dir / "user").exists(), "iterate_reviewer/user prompt missing"

    def test_iterate_prompts_have_placeholders(self, plugin_root):
        """Iterate reviewer user prompt should have {PLAN} and {SPEC} placeholders."""
        user_prompt = (
            Path(plugin_root) / "prompts" / "iterate_reviewer" / "user"
        ).read_text()
        assert "{PLAN}" in user_prompt
        assert "{SPEC}" in user_prompt

    def test_iterate_system_prompt_content(self, plugin_root):
        """Iterate system prompt should focus on single-change review."""
        system_prompt = (
            Path(plugin_root) / "prompts" / "iterate_reviewer" / "system"
        ).read_text()
        assert "single change" in system_prompt.lower()
        assert "existing application" in system_prompt.lower()

    def test_plan_prompts_unchanged(self, plugin_root):
        """Plan reviewer prompts should still exist and be unchanged."""
        prompts_dir = Path(plugin_root) / "prompts" / "plan_reviewer"
        assert (prompts_dir / "system").exists()
        assert (prompts_dir / "user").exists()
        # Plan prompt should mention "specification"
        user_prompt = (prompts_dir / "user").read_text()
        assert "specification" in user_prompt.lower()

    def test_load_iterate_review_prompts(self, plugin_root):
        """load_iterate_review_prompts should return non-empty strings."""
        from lib.prompts import load_iterate_review_prompts

        system, user = load_iterate_review_prompts(plugin_root)
        assert len(system) > 0
        assert len(user) > 0
        assert "{PLAN}" in user
        assert "{SPEC}" in user

    def test_load_iterate_prompts_graceful_fallback(self, tmp_path):
        """If iterate prompts don't exist, should return empty strings."""
        from lib.prompts import load_iterate_review_prompts

        system, user = load_iterate_review_prompts(str(tmp_path))
        assert system == ""
        assert user == ""


class TestReviewSkipWithoutKeys:
    """Test graceful degradation when no API keys are configured."""

    def test_detect_provider_none(self):
        """Without API keys, provider should be 'none'."""
        with patch.dict("os.environ", {}, clear=True):
            # Remove all API keys
            import os
            env_backup = {}
            for key in ["OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"]:
                if key in os.environ:
                    env_backup[key] = os.environ.pop(key)
            try:
                from review import detect_provider
                provider = detect_provider()
                assert provider == "none"
            finally:
                os.environ.update(env_backup)

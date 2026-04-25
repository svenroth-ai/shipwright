"""Tests for plan-local prompt loading.

Plan-local prompts: section_writer (only).
External-review prompts (plan_reviewer, iterate_reviewer) load from shared and
are exercised in shared/tests/test_external_review_prompts.py.
"""

from lib.prompts import load_prompt, load_section_prompt


def test_load_section_prompt(plugin_root):
    prompt = load_section_prompt(plugin_root)
    assert "SECTION_NAME" in prompt
    assert "shipwright-build" in prompt


def test_load_missing_prompt(tmp_path):
    result = load_prompt(tmp_path, "nonexistent", "missing")
    assert result == ""

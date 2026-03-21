"""Tests for prompt loading."""

from lib.prompts import load_prompt, load_review_prompts, load_section_prompt


def test_load_review_prompts(plugin_root):
    system, user = load_review_prompts(plugin_root)
    assert "architect" in system.lower() or "review" in system.lower()
    assert "{PLAN}" in user
    assert "{SPEC}" in user


def test_load_section_prompt(plugin_root):
    prompt = load_section_prompt(plugin_root)
    assert "SECTION_NAME" in prompt
    assert "shipwright-build" in prompt


def test_load_missing_prompt(tmp_path):
    result = load_prompt(tmp_path, "nonexistent", "missing")
    assert result == ""

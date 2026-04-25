"""Tests for shared external review prompt loading."""

import pytest

from lib.external_review_prompts import (
    load_code_review_prompts,
    load_iterate_review_prompts,
    load_plan_review_prompts,
)


@pytest.fixture
def fake_prompts_root(tmp_path):
    """Create a fake shared/prompts/ tree with iterate_reviewer/system + user."""
    iterate_dir = tmp_path / "iterate_reviewer"
    iterate_dir.mkdir()
    (iterate_dir / "system").write_text("You are a senior reviewer.", encoding="utf-8")
    (iterate_dir / "user").write_text(
        "Review this:\n## Spec\n{SPEC}\n## Plan\n{PLAN}\n", encoding="utf-8"
    )
    return tmp_path


def test_load_iterate_review_prompts_with_explicit_root(fake_prompts_root):
    system, user = load_iterate_review_prompts(fake_prompts_root)
    assert system == "You are a senior reviewer."
    assert "{PLAN}" in user
    assert "{SPEC}" in user


def test_load_iterate_review_prompts_missing_returns_empty(tmp_path):
    """If iterate_reviewer/ doesn't exist under prompts_root, return empty strings."""
    system, user = load_iterate_review_prompts(tmp_path)
    assert system == ""
    assert user == ""


def test_load_iterate_review_prompts_default_root_resolves():
    """Without args, function reads from real shared/prompts/iterate_reviewer/.

    Both files MUST ship in the repo — they're how the iterate-mode external
    review actually works in production. A graceful-empty fallback would mask
    a missing-prompts regression (the CLI hardcodes inline defaults at the
    bottom that would silently take over).
    """
    system, user = load_iterate_review_prompts()
    assert system, "shared/prompts/iterate_reviewer/system must ship and be non-empty"
    assert user, "shared/prompts/iterate_reviewer/user must ship and be non-empty"
    assert "{PLAN}" in user
    assert "{SPEC}" in user


def test_load_iterate_review_prompts_string_path_works(fake_prompts_root):
    """Accepts both Path and str."""
    system, user = load_iterate_review_prompts(str(fake_prompts_root))
    assert system == "You are a senior reviewer."
    assert "{PLAN}" in user


@pytest.fixture
def fake_plan_plugin_root(tmp_path):
    """Create a fake plan plugin tree with prompts/plan_reviewer/{system,user}."""
    plan_dir = tmp_path / "prompts" / "plan_reviewer"
    plan_dir.mkdir(parents=True)
    (plan_dir / "system").write_text(
        "You are a senior reviewer for full implementation plans.", encoding="utf-8"
    )
    (plan_dir / "user").write_text(
        "Review this:\n## Specification\n{SPEC}\n## Plan\n{PLAN}\n", encoding="utf-8"
    )
    return tmp_path


def test_load_plan_review_prompts_with_plugin_root(fake_plan_plugin_root):
    system, user = load_plan_review_prompts(fake_plan_plugin_root)
    assert "implementation plans" in system.lower()
    assert "{PLAN}" in user
    assert "{SPEC}" in user


def test_load_plan_review_prompts_missing_returns_empty(tmp_path):
    """Plugin root without prompts/plan_reviewer/ → graceful empty."""
    system, user = load_plan_review_prompts(tmp_path)
    assert system == ""
    assert user == ""


def test_load_plan_review_prompts_string_path_works(fake_plan_plugin_root):
    system, user = load_plan_review_prompts(str(fake_plan_plugin_root))
    assert "{PLAN}" in user
    assert "{SPEC}" in user


# ---- Code-review prompt loading -------------------------------------------


@pytest.fixture
def fake_code_prompts_root(tmp_path):
    """Create a fake shared/prompts/ tree with code_reviewer/system + user."""
    code_dir = tmp_path / "code_reviewer"
    code_dir.mkdir()
    (code_dir / "system").write_text(
        "You are a senior reviewer auditing a code change.", encoding="utf-8"
    )
    (code_dir / "user").write_text(
        "Review this:\n## Spec\n{SPEC}\n## Diff\n{DIFF}\n", encoding="utf-8"
    )
    return tmp_path


def test_load_code_review_prompts_with_explicit_root(fake_code_prompts_root):
    system, user = load_code_review_prompts(fake_code_prompts_root)
    assert system == "You are a senior reviewer auditing a code change."
    assert "{DIFF}" in user
    assert "{SPEC}" in user


def test_load_code_review_prompts_missing_returns_empty(tmp_path):
    """If code_reviewer/ doesn't exist under prompts_root, return empty strings."""
    system, user = load_code_review_prompts(tmp_path)
    assert system == ""
    assert user == ""


def test_load_code_review_prompts_default_root_resolves():
    """Without args, function reads from real shared/prompts/code_reviewer/.

    Both files MUST ship in the repo — they're how the code-review-mode
    external review actually works in production. A graceful-empty fallback
    would mask a missing-prompts regression (the CLI hardcodes inline
    defaults that would silently take over).
    """
    system, user = load_code_review_prompts()
    assert system, "shared/prompts/code_reviewer/system must ship and be non-empty"
    assert user, "shared/prompts/code_reviewer/user must ship and be non-empty"
    assert "{DIFF}" in user
    assert "{SPEC}" in user


def test_load_code_review_prompts_string_path_works(fake_code_prompts_root):
    """Accepts both Path and str."""
    system, user = load_code_review_prompts(str(fake_code_prompts_root))
    assert "{DIFF}" in user
    assert "{SPEC}" in user

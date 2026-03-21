"""Shared test fixtures for shipwright-plan."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture
def plugin_root():
    """Return the plugin root directory."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp_planning(tmp_path):
    """Create a temporary planning directory with sections subdir."""
    planning = tmp_path / "planning"
    planning.mkdir()
    (planning / "sections").mkdir()
    return planning


@pytest.fixture
def sample_spec(tmp_path):
    """Create a sample spec file."""
    spec = tmp_path / "planning" / "spec.md"
    spec.parent.mkdir(exist_ok=True)
    spec.write_text("# Auth Spec\n\nImplement authentication with Supabase.\n", encoding="utf-8")
    return spec


@pytest.fixture
def planning_with_interview(tmp_planning):
    """Planning dir with interview transcript."""
    (tmp_planning / "shipwright_plan_interview.md").write_text(
        "# Interview\n\nQ: What auth method?\nA: Magic link.\n"
    )
    return tmp_planning


@pytest.fixture
def planning_with_plan(planning_with_interview):
    """Planning dir with plan.md containing SECTION_MANIFEST."""
    plan = planning_with_interview / "plan.md"
    plan.write_text(
        "<!-- SECTION_MANIFEST\n01-auth\n02-api\n03-frontend\nEND_MANIFEST -->\n\n"
        "# Implementation Plan\n\nThree sections.\n"
    )
    return planning_with_interview


@pytest.fixture
def planning_with_sections(planning_with_plan):
    """Planning dir with all section files written."""
    sections = planning_with_plan / "sections"
    sections.mkdir(exist_ok=True)
    (sections / "01-auth.md").write_text("# Section: 01-auth\n")
    (sections / "02-api.md").write_text("# Section: 02-api\n")
    (sections / "03-frontend.md").write_text("# Section: 03-frontend\n")
    return planning_with_plan


@pytest.fixture
def sample_prompts(plugin_root):
    """Verify prompt files exist."""
    system = plugin_root / "prompts" / "plan_reviewer" / "system"
    user = plugin_root / "prompts" / "plan_reviewer" / "user"
    assert system.exists(), f"Missing: {system}"
    assert user.exists(), f"Missing: {user}"
    return system, user

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
    planning = tmp_path / ".shipwright" / "planning"
    planning.mkdir(parents=True)
    (planning / "sections").mkdir()
    return planning


@pytest.fixture
def sample_spec(tmp_path):
    """Create a sample spec file."""
    spec = tmp_path / ".shipwright" / "planning" / "spec.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
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
def planning(tmp_path):
    """A planning split whose every gate passes — for
    ``test_check_plan_gates{,_sections}.py``. Defined here (not imported from
    ``_check_plan_gates_support.py``) so it is auto-available to every test
    module without ruff flagging the same-named test-function parameter as
    shadowing an import (F811)."""
    from ._check_plan_gates_support import _build_planning
    return _build_planning(tmp_path)


@pytest.fixture
def bare_planning_dir(tmp_path):
    """A minimal planning dir under the canonical ``.shipwright/planning/``
    location, for the boundary-gate tests in ``test_check_plan_gates.py``."""
    from ._check_plan_gates_support import _build_bare_planning_dir
    return _build_bare_planning_dir(tmp_path)


@pytest.fixture
def sample_prompts(plugin_root):
    """Verify prompt files exist."""
    system = plugin_root / "prompts" / "plan_reviewer" / "system"
    user = plugin_root / "prompts" / "plan_reviewer" / "user"
    assert system.exists(), f"Missing: {system}"
    assert user.exists(), f"Missing: {user}"
    return system, user

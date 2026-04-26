"""Shared test fixtures for shipwright-build."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture
def plugin_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory."""
    project = tmp_path / "my-project"
    project.mkdir()
    (project / "agent_docs").mkdir()
    return project


@pytest.fixture
def sample_section(tmp_path):
    """Create a sample section file."""
    sections = tmp_path / "my-project" / ".shipwright" / "planning" / "sections"
    sections.mkdir(parents=True)
    section = sections / "01-auth.md"
    section.write_text("# Section: 01-auth\n\n## Overview\nImplement auth.\n")
    return section


@pytest.fixture
def tmp_project_with_config(tmp_project):
    """Project with build config."""
    import json
    config = {
        "auto_push": False,
        "conventional_commits": True,
        "sections": [
            {"name": "01-auth", "status": "not_started"},
            {"name": "02-api", "status": "not_started"},
        ],
    }
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )
    return tmp_project

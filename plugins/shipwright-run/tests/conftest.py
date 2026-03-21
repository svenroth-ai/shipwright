"""Shared test fixtures for shipwright-run."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))


@pytest.fixture
def plugin_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory."""
    project = tmp_path / "my-project"
    project.mkdir()
    return project


@pytest.fixture
def existing_project(tmp_project):
    """Project with CLAUDE.md and agent_docs (Extension scope)."""
    (tmp_project / "CLAUDE.md").write_text("# My Project\n")
    (tmp_project / "agent_docs").mkdir()
    (tmp_project / "agent_docs" / "architecture.md").write_text("# Arch\n")
    return tmp_project

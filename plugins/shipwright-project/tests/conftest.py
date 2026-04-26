"""Shared test fixtures for shipwright-project."""

import sys
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture
def tmp_planning(tmp_path):
    """Create a temporary planning directory."""
    planning = tmp_path / ".shipwright" / "planning"
    planning.mkdir(parents=True)
    return planning


@pytest.fixture
def sample_requirements(tmp_path):
    """Create a sample requirements markdown file."""
    req_file = tmp_path / ".shipwright" / "planning" / "requirements.md"
    req_file.parent.mkdir(parents=True, exist_ok=True)
    req_file.write_text(
        "# My Project\n\nBuild a SaaS time tracking app with Supabase and Next.js.\n",
        encoding="utf-8",
    )
    return req_file


@pytest.fixture
def planning_with_interview(tmp_planning):
    """Planning dir with completed interview."""
    interview = tmp_planning / "shipwright_project_interview.md"
    interview.write_text("# Interview Transcript\n\nQ: What is this project?\nA: A time tracker.\n")
    return tmp_planning


@pytest.fixture
def planning_with_manifest(planning_with_interview):
    """Planning dir with completed manifest."""
    manifest = planning_with_interview / "project-manifest.md"
    manifest.write_text(
        "<!-- SPLIT_MANIFEST\n01-auth\n02-dashboard\nEND_MANIFEST -->\n\n# Project Manifest\n\nTwo splits.\n"
    )
    return planning_with_interview


@pytest.fixture
def planning_with_dirs(planning_with_manifest):
    """Planning dir with created split directories."""
    (planning_with_manifest / "01-auth").mkdir()
    (planning_with_manifest / "02-dashboard").mkdir()
    return planning_with_manifest


@pytest.fixture
def planning_with_specs(planning_with_dirs):
    """Planning dir with all specs written."""
    (planning_with_dirs / "01-auth" / "spec.md").write_text("# Auth Spec\n")
    (planning_with_dirs / "02-dashboard" / "spec.md").write_text("# Dashboard Spec\n")
    return planning_with_dirs

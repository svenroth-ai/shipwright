"""Integration tests for shipwright-changelog with real git repos."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.mark.integration
def test_full_changelog_flow(git_repo_with_tag):
    """Test: parse commits → categorize → generate → write changelog."""
    orig = os.getcwd()
    os.chdir(str(git_repo_with_tag))

    try:
        # 1. Parse commits since tag
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "lib" / "git_utils.py"),
             "parse-commits", "--since", "v0.1.0"],
            capture_output=True, text=True, encoding="utf-8",
        )
        parsed = json.loads(result.stdout)
        assert len(parsed) == 3

        # Verify types
        types = {c["type"] for c in parsed}
        assert "feat" in types
        assert "fix" in types
        assert "docs" in types

        # 2. Write parsed to temp file
        commits_file = git_repo_with_tag / "commits.json"
        commits_file.write_text(json.dumps(parsed), encoding="utf-8")

        # 3. Generate changelog
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "lib" / "changelog.py"),
             "generate",
             "--version", "0.2.0",
             "--commits-json", str(commits_file),
             "--changelog-path", str(git_repo_with_tag / "CHANGELOG.md"),
             "--date", "2026-03-21"],
            capture_output=True, text=True, encoding="utf-8",
        )
        output = json.loads(result.stdout)
        assert output["success"] is True

        # 4. Verify changelog file
        changelog = (git_repo_with_tag / "CHANGELOG.md").read_text(encoding="utf-8")
        assert "## [0.2.0] - 2026-03-21" in changelog
        assert "### Added" in changelog
        assert "### Fixed" in changelog
        assert "feat(auth): implement login" in changelog
        assert "fix(api): handle null response" in changelog

    finally:
        os.chdir(orig)


@pytest.mark.integration
def test_setup_changelog_detects_state(git_repo_with_tag):
    """Setup script correctly detects last tag and unreleased commits."""
    orig = os.getcwd()
    os.chdir(str(git_repo_with_tag))

    try:
        plugin_root = str(Path(__file__).resolve().parent.parent)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "checks" / "setup-changelog.py"),
             "--plugin-root", plugin_root],
            capture_output=True, text=True, encoding="utf-8",
        )
        output = json.loads(result.stdout)

        assert output["success"] is True
        assert output["last_tag"] == "v0.1.0"
        assert output["commits_since_tag"] == 3
        assert output["has_unreleased"] is True

    finally:
        os.chdir(orig)


@pytest.mark.integration
def test_version_suggestion(git_repo_with_tag):
    """Version bump suggestion based on commit types."""
    orig = os.getcwd()
    os.chdir(str(git_repo_with_tag))

    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "lib" / "git_utils.py"),
             "suggest-version", "--since", "v0.1.0"],
            capture_output=True, text=True, encoding="utf-8",
        )
        output = json.loads(result.stdout)

        assert output["version"] == "0.2.0"  # Has feat → minor bump
        assert "feature" in output["reason"]

    finally:
        os.chdir(orig)

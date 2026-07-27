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
def test_generate_preserves_existing_history(tmp_path):
    """CLI `generate` must not destroy a hand-written history (trg-6690d175).

    Runs changelog.py as a script, so it also covers the script-mode import
    path that the in-process unit tests never exercise.
    """
    changelog = tmp_path / "CHANGELOG.md"
    original = (
        "# Release History\n\nKept by hand since 2019.\n\n"
        "## [1.0.0] - 2024-01-10\n\n### Added\n- first stable release\n"
    )
    changelog.write_text(original, encoding="utf-8")

    commits_file = tmp_path / "commits.json"
    commits_file.write_text(
        json.dumps([
            {"type": "fix", "scope": "api", "description": "handle null",
             "breaking": False},
        ]),
        encoding="utf-8",
    )

    argv = [
        sys.executable, str(SCRIPTS / "lib" / "changelog.py"), "generate",
        "--version", "1.1.0",
        "--commits-json", str(commits_file),
        "--changelog-path", str(changelog),
        "--date", "2026-07-27",
    ]
    result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr

    content = changelog.read_text(encoding="utf-8")
    assert "# Release History" in content
    assert "Kept by hand since 2019." in content
    assert "## [1.0.0] - 2024-01-10" in content
    assert "- first stable release" in content
    assert content.index("## [1.1.0]") < content.index("## [1.0.0]")

    # Re-running the interrupted release must not duplicate the version.
    result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert changelog.read_text(encoding="utf-8").count("## [1.1.0]") == 1


@pytest.mark.integration
def test_generate_refuses_ambiguous_file_and_leaves_it_untouched(tmp_path):
    """The CLI must stop and say why, not overwrite what it cannot interpret.

    This is the arm that delivers the spec promise "the release stops and says
    why"; the library `raise` alone does not reach the operator.
    """
    changelog = tmp_path / "CHANGELOG.md"
    original = (
        "# Changelog\n\n"
        "## [1.1.0] - 2026-07-27\n\n### Fixed\n- a\n\n"
        "## [1.1.0] - 2026-07-27\n\n### Fixed\n- b\n"
    )
    changelog.write_text(original, encoding="utf-8")

    commits_file = tmp_path / "commits.json"
    commits_file.write_text(
        json.dumps([
            {"type": "fix", "scope": None, "description": "x", "breaking": False},
        ]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable, str(SCRIPTS / "lib" / "changelog.py"), "generate",
            "--version", "1.1.0",
            "--commits-json", str(commits_file),
            "--changelog-path", str(changelog),
            "--date", "2026-07-27",
        ],
        capture_output=True, text=True, encoding="utf-8",
    )

    assert result.returncode == 1
    assert "2 sections" in result.stderr
    assert json.loads(result.stdout)["success"] is False
    assert changelog.read_text(encoding="utf-8") == original


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

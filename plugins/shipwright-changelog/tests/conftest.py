"""Shared test fixtures for shipwright-changelog."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


@pytest.fixture
def plugin_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo with some conventional commits."""
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo),
                    capture_output=True, encoding="utf-8")
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo),
                    capture_output=True, encoding="utf-8")
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo),
                    capture_output=True, encoding="utf-8")

    # Initial commit
    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=str(repo),
                    capture_output=True, encoding="utf-8")

    return repo


@pytest.fixture
def git_repo_with_tag(git_repo):
    """Git repo with a v0.1.0 tag and commits after it."""
    # Tag current state
    subprocess.run(["git", "tag", "v0.1.0"], cwd=str(git_repo),
                    capture_output=True, encoding="utf-8")

    # Add commits after tag
    (git_repo / "auth.ts").write_text("export function login() {}\n")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "feat(auth): implement login"],
                    cwd=str(git_repo), capture_output=True, encoding="utf-8")

    (git_repo / "fix.ts").write_text("// fixed\n")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "fix(api): handle null response"],
                    cwd=str(git_repo), capture_output=True, encoding="utf-8")

    (git_repo / "docs.md").write_text("# Docs\n")
    subprocess.run(["git", "add", "."], cwd=str(git_repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "docs: update README"],
                    cwd=str(git_repo), capture_output=True, encoding="utf-8")

    return git_repo

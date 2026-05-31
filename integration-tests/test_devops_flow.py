"""Integration test: DevOps Flow.

Tests the flow across DevOps plugins:
  shipwright-changelog (with real git)
  shipwright-test (test runner)
  shipwright-deploy (validation only, no real Jelastic calls)
"""

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_PLUGIN = REPO_ROOT / "plugins" / "shipwright-changelog"
TEST_PLUGIN = REPO_ROOT / "plugins" / "shipwright-test"
DEPLOY_PLUGIN = REPO_ROOT / "plugins" / "shipwright-deploy"
SHARED_SCRIPTS = REPO_ROOT / "shared" / "scripts"


def run_script(script_path: str, args: list[str], cwd: str = None, env: dict = None) -> dict:
    """Run a script and return parsed JSON."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    result = subprocess.run(
        [sys.executable, script_path] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=cwd, env=run_env,
    )
    return json.loads(result.stdout)


def make_git_repo(path: Path, commits: list[str]) -> Path:
    """Create a git repo with conventional commits."""
    path.mkdir(exist_ok=True)

    subprocess.run(["git", "init", "-b", "main"], cwd=str(path),
                    capture_output=True, encoding="utf-8")
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(path),
                    capture_output=True, encoding="utf-8")
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(path),
                    capture_output=True, encoding="utf-8")

    for i, msg in enumerate(commits):
        (path / f"file{i}.txt").write_text(f"content {i}\n")
        subprocess.run(["git", "add", "."], cwd=str(path), capture_output=True)
        subprocess.run(["git", "commit", "-m", msg], cwd=str(path),
                        capture_output=True, encoding="utf-8")

    return path


class TestChangelogFlow:
    """Changelog plugin with real git repos."""

    def test_setup_detects_commits(self, tmp_path):
        """Setup script finds unreleased commits."""
        repo = make_git_repo(tmp_path / "project", [
            "chore: initial commit",
            "feat(auth): add login",
            "fix(api): handle null",
        ])

        orig = os.getcwd()
        os.chdir(str(repo))
        try:
            output = run_script(
                str(CHANGELOG_PLUGIN / "scripts" / "checks" / "setup-changelog.py"),
                ["--plugin-root", str(CHANGELOG_PLUGIN)],
            )
            assert output["success"] is True
            assert output["commits_since_tag"] == 3
            assert output["has_unreleased"] is True
        finally:
            os.chdir(orig)

    def test_parse_and_categorize(self, tmp_path):
        """Parse commits and categorize for changelog."""
        repo = make_git_repo(tmp_path / "project", [
            "feat(auth): add login",
            "fix(api): handle null",
            "docs: update README",
        ])

        # Tag initial state and add more commits
        subprocess.run(["git", "tag", "v0.1.0"], cwd=str(repo),
                        capture_output=True, encoding="utf-8")

        (repo / "new.ts").write_text("new\n")
        subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat(dashboard): add charts"],
                        cwd=str(repo), capture_output=True, encoding="utf-8")

        orig = os.getcwd()
        os.chdir(str(repo))
        try:
            # Parse commits since tag
            result = subprocess.run(
                [sys.executable, str(CHANGELOG_PLUGIN / "scripts" / "lib" / "git_utils.py"),
                 "parse-commits", "--since", "v0.1.0"],
                capture_output=True, text=True, encoding="utf-8",
            )
            parsed = json.loads(result.stdout)
            assert len(parsed) == 1
            assert parsed[0]["type"] == "feat"

            # Generate changelog
            commits_file = repo / "commits.json"
            commits_file.write_text(json.dumps(parsed))

            result = subprocess.run(
                [sys.executable, str(CHANGELOG_PLUGIN / "scripts" / "lib" / "changelog.py"),
                 "generate",
                 "--version", "0.2.0",
                 "--commits-json", str(commits_file),
                 "--changelog-path", str(repo / "CHANGELOG.md"),
                 "--date", "2026-03-21"],
                capture_output=True, text=True, encoding="utf-8",
            )
            output = json.loads(result.stdout)
            assert output["success"] is True

            changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
            assert "[0.2.0]" in changelog
            assert "feat(dashboard): add charts" in changelog

        finally:
            os.chdir(orig)


class TestTestRunnerFlow:
    """Test runner with mock commands."""

    def test_run_echo_as_test(self):
        """Test runner can execute arbitrary commands."""
        output = run_script(
            str(TEST_PLUGIN / "scripts" / "lib" / "test_runner.py"),
            ["--command", "echo 10 passed", "--layer", "unit"],
        )
        assert output["success"] is True
        assert output["passed"] == 10

    def test_profile_command_mapping(self):
        """Profile → test command mapping works."""
        output = run_script(
            str(TEST_PLUGIN / "scripts" / "lib" / "test_runner.py"),
            ["--profile", "supabase-nextjs", "--command", "echo ok", "--layer", "unit"],
        )
        assert output["success"] is True


class TestDeployValidation:
    """Deploy validation (no real API calls)."""

    def test_validate_with_token(self):
        output = run_script(
            str(DEPLOY_PLUGIN / "scripts" / "checks" / "validate-deploy.py"),
            [],
            env={"JELASTIC_TOKEN": "test-token"},
        )
        assert output["success"] is True
        assert output["jelastic_token"] is True

    def test_validate_without_token(self):
        env = os.environ.copy()
        env.pop("JELASTIC_TOKEN", None)
        result = subprocess.run(
            [sys.executable, str(DEPLOY_PLUGIN / "scripts" / "checks" / "validate-deploy.py")],
            capture_output=True, text=True, encoding="utf-8",
            env=env,
        )
        output = json.loads(result.stdout)
        assert output["success"] is False


class TestSmokeTestShared:
    """Smoke test used by both test and deploy plugins."""

    def test_smoke_test_structure(self):
        """Verify smoke_test.py returns expected fields."""
        output = run_script(
            str(SHARED_SCRIPTS / "smoke_test.py"),
            ["--url", "http://localhost:19999", "--timeout", "1"],
        )
        assert "success" in output
        assert "url" in output
        assert "status_code" in output
        assert "response_time_ms" in output
        assert output["success"] is False  # nothing running on 19999


class TestCrossPluginArtifacts:
    """Verify DevOps plugins work with artifacts from Core Trilogy."""

    def test_changelog_on_trilogy_commits(self, tmp_path):
        """Changelog can process commits from shipwright-build style."""
        repo = make_git_repo(tmp_path / "project", [
            "chore: initial setup",
        ])

        subprocess.run(["git", "tag", "v0.1.0"], cwd=str(repo),
                        capture_output=True, encoding="utf-8")

        # Add build-style commits
        for msg in [
            "feat(auth): implement magic link authentication",
            "test(auth): add E2E test for login flow",
            "fix(auth): handle expired token gracefully",
            "chore(deps): upgrade @supabase/supabase-js to 2.99",
        ]:
            (repo / f"f{hash(msg)}.txt").write_text("x\n")
            subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
            subprocess.run(["git", "commit", "-m", msg], cwd=str(repo),
                            capture_output=True, encoding="utf-8")

        orig = os.getcwd()
        os.chdir(str(repo))
        try:
            result = subprocess.run(
                [sys.executable, str(CHANGELOG_PLUGIN / "scripts" / "lib" / "git_utils.py"),
                 "suggest-version", "--since", "v0.1.0"],
                capture_output=True, text=True, encoding="utf-8",
            )
            output = json.loads(result.stdout)
            assert output["version"] == "0.2.0"  # Has feat → minor bump
        finally:
            os.chdir(orig)

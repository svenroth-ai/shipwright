"""Integration test: shipwright-run orchestrates the full pipeline.

Tests the orchestrator's ability to:
1. Infer settings from description
2. Write config
3. Track pipeline progress across all plugins
4. Resume from any point
5. Handle all three scope flows

Note: These tests use --force on update-step calls because integration
tests don't produce the full set of canon artifacts (events, dashboard,
handoff, etc.) that the phase validators check since iterate 12.1.
The canon compliance is tested separately in shared/tests/.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_PLUGIN = REPO_ROOT / "plugins" / "shipwright-run"
PROJECT_PLUGIN = REPO_ROOT / "plugins" / "shipwright-project"
PLAN_PLUGIN = REPO_ROOT / "plugins" / "shipwright-plan"
BUILD_PLUGIN = REPO_ROOT / "plugins" / "shipwright-build"
CHANGELOG_PLUGIN = REPO_ROOT / "plugins" / "shipwright-changelog"


def run_script(script_path: str, args: list[str], cwd: str = None) -> dict:
    # Inherit parent env minus scanner-availability signals so the
    # autouse fixture in conftest.py actually reaches subprocesses too.
    # (Without this the subprocess re-evaluates _check_security_available
    # against the real PATH and silently enables the security phase when
    # semgrep is installed, which makes pipeline-shape assertions
    # non-deterministic per host.)
    env = os.environ.copy()
    env.pop("AIKIDO_CLIENT_ID", None)
    env.pop("SHIPWRIGHT_SCANNER_BACKEND", None)
    env["SHIPWRIGHT_TEST_DISABLE_OSS_SCANNERS"] = "1"
    result = subprocess.run(
        [sys.executable, script_path] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=cwd, env=env,
    )
    return json.loads(result.stdout)


class TestFullPipelineE2E:
    """Simulate the full pipeline: run → project → plan → build → changelog."""

    def test_full_pipeline(self, tmp_path):
        """Complete pipeline from inference to changelog."""
        project = tmp_path / "todo-app"
        project.mkdir()
        planning = project / ".shipwright" / "planning"
        planning.mkdir(parents=True)

        # Init git
        subprocess.run(["git", "init", "-b", "main"], cwd=str(project),
                        capture_output=True, encoding="utf-8")
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                        cwd=str(project), capture_output=True, encoding="utf-8")
        subprocess.run(["git", "config", "user.name", "Test"],
                        cwd=str(project), capture_output=True, encoding="utf-8")

        # === Phase 1: shipwright-run — Inference + Config ===
        result = run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "inference.py"),
            ["--description", "Build a SaaS todo app with Supabase and Next.js"],
        )
        assert result["scope"] == "full_app"
        assert result["profile"] == "supabase-nextjs"
        assert result["profile_confidence"] == "high"

        result = run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
            ["write-config",
             "--scope", "full_app",
             "--profile", "supabase-nextjs",
             "--autonomy", "guided",
             "--project-root", str(project)],
        )
        assert result["current_step"] == "project"
        assert (project / "shipwright_run_config.json").exists()

        # === Phase 2: shipwright-project ===
        req = planning / "requirements.md"
        req.write_text("# Todo App\n\nBuild a todo app with Supabase.\n")

        result = run_script(
            str(PROJECT_PLUGIN / "scripts" / "checks" / "setup-session.py"),
            ["--file", str(req), "--plugin-root", str(PROJECT_PLUGIN)],
        )
        assert result["success"] is True

        # Simulate project phase completion
        (planning / "shipwright_project_interview.md").write_text("# Interview\nDone.\n")
        (planning / "project-manifest.md").write_text(
            "<!-- SPLIT_MANIFEST\n01-auth\nEND_MANIFEST -->\n"
        )
        subprocess.run(
            [sys.executable, str(PROJECT_PLUGIN / "scripts" / "checks" / "create-split-dirs.py"),
             "--planning-dir", str(planning)],
            capture_output=True, encoding="utf-8",
        )
        (planning / "01-auth" / "spec.md").write_text("# Auth Spec\n")

        # Update orchestrator: project complete (--force skips canon validation
        # which requires artifacts not produced in integration tests)
        run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
            ["update-step", "--project-root", str(project),
             "--step", "project", "--status", "complete", "--force"],
        )

        # === Phase 2.5: shipwright-design (skip in test, mark complete) ===
        run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
            ["update-step", "--project-root", str(project),
             "--step", "design", "--status", "complete", "--force"],
        )

        # === Phase 3: shipwright-plan ===
        auth_dir = planning / "01-auth"
        result = run_script(
            str(PLAN_PLUGIN / "scripts" / "checks" / "setup-planning-session.py"),
            ["--file", str(auth_dir / "spec.md"), "--plugin-root", str(PLAN_PLUGIN)],
        )
        assert result["success"] is True

        # Simulate plan phase
        (auth_dir / "shipwright_plan_interview.md").write_text("# Plan Interview\nDone.\n")
        (auth_dir / "plan.md").write_text(
            "<!-- SECTION_MANIFEST\n01-models\nEND_MANIFEST -->\n"
        )
        sections = auth_dir / "sections"
        sections.mkdir(exist_ok=True)
        (sections / "01-models.md").write_text("# Section: 01-models\n")

        run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
            ["update-step", "--project-root", str(project),
             "--step", "plan", "--status", "complete", "--force"],
        )

        # === Phase 4: shipwright-build ===
        result = run_script(
            str(BUILD_PLUGIN / "scripts" / "checks" / "setup_implementation_session.py"),
            ["--file", str(sections / "01-models.md"), "--plugin-root", str(BUILD_PLUGIN)],
        )
        assert result["success"] is True
        assert result["section_name"] == "01-models"

        # Simulate build artifacts
        (project / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
        run_script(
            str(BUILD_PLUGIN / "scripts" / "tools" / "update_section_state.py"),
            ["--section", "01-models", "--status", "complete",
             "--commit", "abc123", "--project-root", str(project)],
        )

        # Add a file and commit for changelog
        (project / "src").mkdir(exist_ok=True)
        (project / "src" / "auth.ts").write_text("export function login() {}\n")
        subprocess.run(["git", "add", "."], cwd=str(project), capture_output=True)
        subprocess.run(["git", "commit", "-m", "feat(auth): implement login"],
                        cwd=str(project), capture_output=True, encoding="utf-8")

        run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
            ["update-step", "--project-root", str(project),
             "--step", "build", "--status", "complete", "--force"],
        )

        # Skip test (no real infra)
        run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
            ["update-step", "--project-root", str(project),
             "--step", "test", "--status", "complete", "--force"],
        )

        # === Phase 5: shipwright-changelog ===
        orig = os.getcwd()
        os.chdir(str(project))
        try:
            result = run_script(
                str(CHANGELOG_PLUGIN / "scripts" / "checks" / "setup-changelog.py"),
                ["--plugin-root", str(CHANGELOG_PLUGIN)],
            )
            assert result["success"] is True
            assert result["has_unreleased"] is True
        finally:
            os.chdir(orig)

        run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
            ["update-step", "--project-root", str(project),
             "--step", "changelog", "--status", "complete", "--force"],
        )

        # Skip deploy (no real infra). Compliance is no longer a pipeline
        # phase (plan v7 Option Z).
        run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
            ["update-step", "--project-root", str(project),
             "--step", "deploy", "--status", "complete", "--force"],
        )

        # === Verify final state ===
        config = json.loads(
            (project / "shipwright_run_config.json").read_text(encoding="utf-8")
        )
        assert config["status"] == "complete"
        assert config["current_step"] is None
        assert set(config["completed_steps"]) == {
            "project", "design", "plan", "build", "test", "changelog", "deploy"
        }


class TestResumeFromAnyPoint:
    """Verify orchestrator resume works from every pipeline step."""

    def test_resume_after_each_step(self, tmp_path):
        project = tmp_path / "resume-test"
        project.mkdir()

        # Create config
        run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
            ["write-config",
             "--scope", "full_app",
             "--profile", "supabase-nextjs",
             "--project-root", str(project)],
        )

        # Pipeline order: project → design → plan → build → test →
        # changelog → deploy (matches PIPELINE_STEPS in orchestrator.py).
        # Compliance is no longer a pipeline phase (plan v7 Option Z) —
        # it runs as an auto-background side-effect + on-demand detective audit.
        expected_next = {
            "project": "design",
            "design": "plan",
            "plan": "build",
            "build": "test",
            "test": "changelog",
            "changelog": "deploy",
        }

        for step, expected in expected_next.items():
            # --force skips canon validation (no artifacts in this test)
            run_script(
                str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
                ["update-step", "--project-root", str(project),
                 "--step", step, "--status", "complete", "--force"],
            )
            result = run_script(
                str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
                ["get-next-step", "--project-root", str(project)],
            )
            assert result["next_step"] == expected, f"After {step}, expected {expected} but got {result['next_step']}"

        # After deploy, pipeline is complete
        run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
            ["update-step", "--project-root", str(project),
             "--step", "deploy", "--status", "complete", "--force"],
        )
        result = run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "orchestrator.py"),
            ["get-next-step", "--project-root", str(project)],
        )
        assert result["next_step"] is None


class TestIterateMode:
    """Verify iterate mode detection and extension scope inference."""

    def test_existing_project_infers_extension(self, tmp_path):
        """Existing project with CLAUDE.md + agent_docs → extension scope.

        The --iterate flag is deprecated since /shipwright-iterate has its
        own skill entry point. inference.py only distinguishes full_app
        (greenfield) from extension (existing project).
        """
        project = tmp_path / "existing-app"
        project.mkdir()
        (project / "CLAUDE.md").write_text("# Existing App\n")
        (project / ".shipwright" / "agent_docs").mkdir(parents=True)

        result = run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "inference.py"),
            ["--description", "Add dark mode toggle",
             "--project-root", str(project)],
        )

        assert result["scope"] == "extension"

    def test_extension_without_iterate_flag(self, tmp_path):
        """Existing project without --iterate → extension scope."""
        project = tmp_path / "existing-app"
        project.mkdir()
        (project / "CLAUDE.md").write_text("# Existing App\n")
        (project / ".shipwright" / "agent_docs").mkdir(parents=True)

        result = run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "inference.py"),
            ["--description", "Add user management",
             "--project-root", str(project)],
        )

        assert result["scope"] == "extension"

    def test_iterate_flag_deprecated_still_accepted(self, tmp_path):
        """The --iterate flag is accepted without error (backward compat)
        but doesn't change the output — scope is still inferred from
        filesystem state, not the flag.
        """
        project = tmp_path / "existing-app"
        project.mkdir()
        (project / "CLAUDE.md").write_text("# Existing App\n")
        (project / ".shipwright" / "agent_docs").mkdir(parents=True)

        result = run_script(
            str(RUN_PLUGIN / "scripts" / "lib" / "inference.py"),
            ["--description", "Fix login bug",
             "--project-root", str(project),
             "--iterate"],
        )

        # --iterate is deprecated and ignored; scope comes from filesystem
        assert result["scope"] == "extension"

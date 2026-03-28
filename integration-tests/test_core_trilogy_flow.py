"""Integration test: Core Trilogy Flow.

Simulates the complete script flow across all three plugins:
  shipwright-project → shipwright-plan → shipwright-build

Tests that scripts communicate correctly via config files and that
all expected artifacts are generated.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    BUILD_PLUGIN,
    PLAN_PLUGIN,
    PROJECT_PLUGIN,
    run_script,
)
from tools.write_decision_log import append_decision


class TestCoreTrilogyFlow:
    """End-to-end test of the trilogy script flow."""

    # ── Phase 1: shipwright-project ──

    def test_01_project_setup(self, trilogy_project):
        """shipwright-project setup creates session state."""
        req = trilogy_project / "planning" / "requirements.md"

        result = run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req),
            "--plugin-root", str(PROJECT_PLUGIN),
            "--session-id", "trilogy-test",
        ])

        assert result["success"] is True
        assert result["mode"] == "new"
        assert result["input_mode"] == "file"
        assert result["resume_from_step"] == 1

        # Verify session state file was created
        state_file = trilogy_project / "planning" / "shipwright_project_session.json"
        assert state_file.exists()

    def test_02_project_chat_mode(self, tmp_path):
        """shipwright-project also works in chat mode (no file)."""
        planning = tmp_path / "chat-project" / "planning"

        result = run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--planning-dir", str(planning),
            "--plugin-root", str(PROJECT_PLUGIN),
            "--input-mode", "chat",
            "--session-id", "chat-test",
        ])

        assert result["success"] is True
        assert result["input_mode"] == "chat"
        assert result["initial_file"] is None
        assert planning.is_dir()

    def test_03_project_simulate_interview_and_manifest(self, trilogy_project):
        """Simulate interview + manifest creation (normally done by SKILL.md)."""
        planning = trilogy_project / "planning"

        # Setup first
        req = planning / "requirements.md"
        run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req),
            "--plugin-root", str(PROJECT_PLUGIN),
            "--session-id", "trilogy-test",
        ])

        # Simulate interview output
        interview = planning / "shipwright_project_interview.md"
        interview.write_text(
            "# Interview Transcript\n\n"
            "Q: What are you building?\n"
            "A: A minimal todo app with Supabase + Next.js\n\n"
            "Q: How should we split the work?\n"
            "A: Auth first, then data model, then frontend.\n",
            encoding="utf-8",
        )

        # Simulate manifest
        manifest = planning / "project-manifest.md"
        manifest.write_text(
            "<!-- SPLIT_MANIFEST\n"
            "01-auth\n"
            "02-data-model\n"
            "03-frontend\n"
            "END_MANIFEST -->\n\n"
            "# Project Manifest\n\n"
            "Three splits for the todo app.\n",
            encoding="utf-8",
        )

        # Create split directories
        result = run_script(PROJECT_PLUGIN, "checks", "create-split-dirs.py", [
            "--planning-dir", str(planning),
        ])

        assert result["success"] is True
        assert result["created"] == ["01-auth", "02-data-model", "03-frontend"]
        assert (planning / "01-auth").is_dir()
        assert (planning / "02-data-model").is_dir()
        assert (planning / "03-frontend").is_dir()

    def test_04_project_write_specs_and_config(self, trilogy_project):
        """Write specs + project config (simulates SKILL.md Steps 6-7)."""
        planning = trilogy_project / "planning"

        # Setup + simulate prior steps
        req = planning / "requirements.md"
        run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req),
            "--plugin-root", str(PROJECT_PLUGIN),
        ])

        (planning / "shipwright_project_interview.md").write_text("# Interview\n")
        (planning / "project-manifest.md").write_text(
            "<!-- SPLIT_MANIFEST\n01-auth\n02-data-model\nEND_MANIFEST -->\n"
        )
        run_script(PROJECT_PLUGIN, "checks", "create-split-dirs.py", [
            "--planning-dir", str(planning),
        ])

        # Write specs (normally Claude generates these from IREB template)
        (planning / "01-auth" / "spec.md").write_text(
            "# Authentication\n\n> Split 01 of 02\n\n"
            "## 1. Purpose & Scope\nAuth with Supabase.\n\n"
            "## 2. Functional Requirements\n\n"
            "| ID | Requirement | Priority |\n"
            "|----|-------------|----------|\n"
            "| FR-01.01 | The system SHALL allow login via email/password | Must |\n",
            encoding="utf-8",
        )
        (planning / "02-data-model" / "spec.md").write_text(
            "# Data Model\n\n> Split 02 of 02\n\n"
            "## 1. Purpose & Scope\nTodo CRUD with Supabase.\n",
            encoding="utf-8",
        )

        # Write project config (Step 7)
        result = run_script(PROJECT_PLUGIN, "checks", "write-project-config.py", [
            "--planning-dir", str(planning),
            "--profile", "supabase-nextjs",
            "--scope", "full_app",
            "--project-root", str(trilogy_project),
        ])

        assert result["status"] == "complete"
        assert result["profile"] == "supabase-nextjs"
        assert len(result["splits"]) == 2

        # Verify config file
        config_path = trilogy_project / "shipwright_project_config.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        assert config["scope"] == "full_app"

    # ── Phase 2: shipwright-plan ──

    def test_05_plan_setup(self, trilogy_project):
        """shipwright-plan setup works with spec from project phase."""
        planning = trilogy_project / "planning"
        self._setup_project_phase(trilogy_project)

        spec = planning / "01-auth" / "spec.md"

        result = run_script(PLAN_PLUGIN, "checks", "setup-planning-session.py", [
            "--file", str(spec),
            "--plugin-root", str(PLAN_PLUGIN),
            "--session-id", "trilogy-plan-test",
        ])

        assert result["success"] is True
        assert result["mode"] == "new"
        assert result["resume_from_step"] == 1
        assert (spec.parent / "sections").is_dir()

    def test_06_plan_simulate_full_flow(self, trilogy_project):
        """Simulate plan writing + section splitting."""
        planning = trilogy_project / "planning"
        self._setup_project_phase(trilogy_project)

        auth_dir = planning / "01-auth"

        # Simulate interview
        (auth_dir / "shipwright_plan_interview.md").write_text(
            "# Planning Interview\n\nQ: Auth approach?\nA: Supabase magic link.\n"
        )

        # Simulate plan with sections
        (auth_dir / "plan.md").write_text(
            "<!-- SECTION_MANIFEST\n01-models\n02-routes\n03-ui\nEND_MANIFEST -->\n\n"
            "# Auth Implementation Plan\n\nThree sections.\n"
        )

        # Write section files
        sections = auth_dir / "sections"
        sections.mkdir(exist_ok=True)
        for name in ["01-models", "02-routes", "03-ui"]:
            (sections / f"{name}.md").write_text(f"# Section: {name}\n\n## Overview\n")

        # Verify with check-sections
        result = run_script(PLAN_PLUGIN, "checks", "check-sections.py", [
            "--planning-dir", str(auth_dir),
        ])

        assert result["success"] is True
        assert result["missing"] == []
        assert len(result["written"]) == 3

    # ── Phase 3: shipwright-build ──

    def test_07_build_setup(self, trilogy_project):
        """shipwright-build setup works with section from plan phase."""
        planning = trilogy_project / "planning"
        self._setup_project_phase(trilogy_project)
        self._setup_plan_phase(trilogy_project)

        section = planning / "01-auth" / "sections" / "01-models.md"

        result = run_script(BUILD_PLUGIN, "checks", "setup_implementation_session.py", [
            "--file", str(section),
            "--plugin-root", str(BUILD_PLUGIN),
            "--session-id", "trilogy-build-test",
        ])

        assert result["success"] is True
        assert result["section_name"] == "01-models"
        assert result["branch_name"] == "shipwright/01-models"

    def test_08_build_tools(self, trilogy_project):
        """shipwright-build tools work (decision log, section state, handoff)."""
        self._setup_project_phase(trilogy_project)

        # Create agent_docs
        (trilogy_project / "agent_docs").mkdir(exist_ok=True)

        # Update section state
        result = run_script(BUILD_PLUGIN, "tools", "update_section_state.py", [
            "--section", "01-models",
            "--status", "complete",
            "--commit", "abc123def",
            "--project-root", str(trilogy_project),
        ])
        assert result["success"] is True

        # Write decision log
        adr_num = append_decision(
            trilogy_project,
            section_ref="Build — 01-models",
            commit_hash="abc123def",
            context="Better UX for initial MVP",
            decision="Use Supabase magic link",
            consequences="No password management needed",
            rejected="Password auth",
        )
        assert adr_num >= 1

        # Generate handoff
        result = run_script(BUILD_PLUGIN, "tools", "generate_session_handoff.py", [
            "--project-root", str(trilogy_project),
            "--section", "01-models",
            "--status", "complete",
        ])
        assert result["success"] is True

        # Verify all artifacts exist
        assert (trilogy_project / "shipwright_build_config.json").exists()
        assert (trilogy_project / "agent_docs" / "decision_log.md").exists()
        assert (trilogy_project / "agent_docs" / "session_handoff.md").exists()

        # Verify decision log content
        log = (trilogy_project / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")
        assert "Supabase magic link" in log
        assert "ADR-001" in log

    # ── Full flow ──

    def test_09_full_trilogy_artifacts(self, trilogy_project):
        """Verify all artifacts exist after complete trilogy flow."""
        planning = trilogy_project / "planning"
        self._setup_project_phase(trilogy_project)
        self._setup_plan_phase(trilogy_project)

        # Simulate build phase artifacts
        (trilogy_project / "agent_docs").mkdir(exist_ok=True)

        run_script(BUILD_PLUGIN, "tools", "update_section_state.py", [
            "--section", "01-models",
            "--status", "complete",
            "--commit", "abc123",
            "--project-root", str(trilogy_project),
        ])

        append_decision(
            trilogy_project,
            section_ref="Build — 01-models",
            commit_hash="abc123",
            context="Testing",
            decision="Test decision",
            consequences="None",
        )

        # ── Verify complete artifact set ──
        # Project phase artifacts
        assert (planning / "requirements.md").exists()
        assert (planning / "shipwright_project_interview.md").exists()
        assert (planning / "project-manifest.md").exists()
        assert (planning / "shipwright_project_session.json").exists()
        assert (planning / "01-auth" / "spec.md").exists()
        assert (planning / "02-data-model" / "spec.md").exists()
        assert (trilogy_project / "shipwright_project_config.json").exists()

        # Plan phase artifacts
        assert (planning / "01-auth" / "plan.md").exists()
        assert (planning / "01-auth" / "shipwright_plan_interview.md").exists()
        assert (planning / "01-auth" / "shipwright_plan_session.json").exists()
        assert (planning / "01-auth" / "sections" / "01-models.md").exists()

        # Build phase artifacts
        assert (trilogy_project / "shipwright_build_config.json").exists()
        assert (trilogy_project / "agent_docs" / "decision_log.md").exists()

    # ── Helpers ──

    def _setup_project_phase(self, project: Path):
        """Simulate completed project phase."""
        planning = project / "planning"
        req = planning / "requirements.md"

        if not req.exists():
            planning.mkdir(exist_ok=True)
            req.write_text("# Test Project\n\nBuild something.\n")

        run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req),
            "--plugin-root", str(PROJECT_PLUGIN),
        ])

        (planning / "shipwright_project_interview.md").write_text("# Interview\nDone.\n")
        (planning / "project-manifest.md").write_text(
            "<!-- SPLIT_MANIFEST\n01-auth\n02-data-model\nEND_MANIFEST -->\n"
        )

        run_script(PROJECT_PLUGIN, "checks", "create-split-dirs.py", [
            "--planning-dir", str(planning),
        ])

        (planning / "01-auth" / "spec.md").write_text("# Auth Spec\n\n## 1. Purpose\nAuth.\n")
        (planning / "02-data-model" / "spec.md").write_text("# Data Spec\n\n## 1. Purpose\nData.\n")

        run_script(PROJECT_PLUGIN, "checks", "write-project-config.py", [
            "--planning-dir", str(planning),
            "--profile", "supabase-nextjs",
            "--scope", "full_app",
            "--project-root", str(project),
        ])

    def _setup_plan_phase(self, project: Path):
        """Simulate completed plan phase for 01-auth."""
        auth_dir = project / "planning" / "01-auth"

        run_script(PLAN_PLUGIN, "checks", "setup-planning-session.py", [
            "--file", str(auth_dir / "spec.md"),
            "--plugin-root", str(PLAN_PLUGIN),
        ])

        (auth_dir / "shipwright_plan_interview.md").write_text("# Planning Interview\nDone.\n")
        (auth_dir / "plan.md").write_text(
            "<!-- SECTION_MANIFEST\n01-models\n02-routes\nEND_MANIFEST -->\n\n# Plan\n"
        )

        sections = auth_dir / "sections"
        sections.mkdir(exist_ok=True)
        (sections / "01-models.md").write_text("# Section: 01-models\n")
        (sections / "02-routes.md").write_text("# Section: 02-routes\n")

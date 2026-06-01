"""Integration test: State Recovery across plugins.

Tests that each plugin correctly detects state from file existence
and resumes from the right step — including cross-plugin scenarios
where one plugin's output is another's input.
"""

import json
from pathlib import Path


from conftest import (
    BUILD_PLUGIN,
    PLAN_PLUGIN,
    PROJECT_PLUGIN,
    SHARED_SCRIPTS,
    run_script,
)


def _assert_no_legacy_artifact_dirs(project_root: Path) -> None:
    """Layer 3 negative-assertion (mirror of test_core_trilogy_flow):
    fail if any `migrated` artifact appeared at its legacy top-level location.

    `in_progress` is intentionally warn-only during the migration window —
    plugin code migrates incrementally across Sub-Iterates B-E, so legacy
    paths are expected until F flips status to `migrated`.

    Loaded by file-spec to avoid sys.modules poisoning the `lib` namespace
    for plugin tests that import a different `lib` package.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_artifact_migrations_layer3",
        SHARED_SCRIPTS / "lib" / "artifact_migrations.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for migration in module.ARTIFACT_MIGRATIONS:
        if migration["status"] != "migrated":
            continue
        legacy = project_root / migration["legacy_dirname"]
        assert not legacy.exists(), (
            f"Migration drift: artifact `{migration['name']}` produced legacy "
            f"directory {legacy} (status: {migration['status']}). Canonical: "
            f"{project_root / migration['canonical']}"
        )


def _write_review_marker(planning_dir: Path, status: str = "completed") -> None:
    """Simulate a completed Step 5 external review pass.

    Required since /shipwright-plan v0.3.0 — resume detection gates all
    post-Step-5 transitions on the presence of this marker.
    """
    (planning_dir / "external_review_state.json").write_text(
        json.dumps({
            "status": status,
            "provider": "openrouter",
            "findings_count": 0,
            "self_review_fallback_ran": False,
            "timestamp": "2026-04-14T00:00:00Z",
        })
    )


class TestProjectStateRecovery:
    """shipwright-project resume from various checkpoints."""

    def test_resume_after_interview(self, trilogy_project):
        """Resume detects interview exists → skip to step 2."""
        planning = trilogy_project / ".shipwright" / "planning"
        req = planning / "requirements.md"

        # First run
        run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req), "--plugin-root", str(PROJECT_PLUGIN),
        ])

        # Simulate interview
        (planning / "shipwright_project_interview.md").write_text("# Interview\n")

        # Resume should detect step 2
        result = run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req), "--plugin-root", str(PROJECT_PLUGIN),
        ])
        assert result["mode"] == "resume"
        assert result["resume_from_step"] == 2

    def test_resume_after_manifest(self, trilogy_project):
        """Resume detects manifest → skip to step 4."""
        planning = trilogy_project / ".shipwright" / "planning"
        req = planning / "requirements.md"

        run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req), "--plugin-root", str(PROJECT_PLUGIN),
        ])

        (planning / "shipwright_project_interview.md").write_text("# Interview\n")
        (planning / "project-manifest.md").write_text(
            "<!-- SPLIT_MANIFEST\n01-core\nEND_MANIFEST -->\n"
        )

        result = run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req), "--plugin-root", str(PROJECT_PLUGIN),
        ])
        assert result["resume_from_step"] == 4

    def test_resume_after_dirs(self, trilogy_project):
        """Resume detects directories → skip to step 6."""
        planning = trilogy_project / ".shipwright" / "planning"
        req = planning / "requirements.md"

        run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req), "--plugin-root", str(PROJECT_PLUGIN),
        ])

        (planning / "shipwright_project_interview.md").write_text("# Interview\n")
        (planning / "project-manifest.md").write_text(
            "<!-- SPLIT_MANIFEST\n01-core\nEND_MANIFEST -->\n"
        )
        (planning / "01-core").mkdir()

        result = run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req), "--plugin-root", str(PROJECT_PLUGIN),
        ])
        assert result["resume_from_step"] == 6

    def test_resume_after_specs(self, trilogy_project):
        """Resume detects all specs → skip to step 7 (scaffolding)."""
        planning = trilogy_project / ".shipwright" / "planning"
        req = planning / "requirements.md"

        run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req), "--plugin-root", str(PROJECT_PLUGIN),
        ])

        (planning / "shipwright_project_interview.md").write_text("# Interview\n")
        (planning / "project-manifest.md").write_text(
            "<!-- SPLIT_MANIFEST\n01-core\nEND_MANIFEST -->\n"
        )
        (planning / "01-core").mkdir()
        (planning / "01-core" / "spec.md").write_text("# Spec\n")

        result = run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req), "--plugin-root", str(PROJECT_PLUGIN),
        ])
        assert result["resume_from_step"] == 7

    def test_force_overwrite(self, trilogy_project):
        """--force resets session to new."""
        planning = trilogy_project / ".shipwright" / "planning"
        req = planning / "requirements.md"

        # Create established session
        run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req), "--plugin-root", str(PROJECT_PLUGIN),
        ])
        (planning / "shipwright_project_interview.md").write_text("# Interview\n")

        # Force should reset
        result = run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(req), "--plugin-root", str(PROJECT_PLUGIN), "--force",
        ])
        assert result["mode"] == "new"


class TestPlanStateRecovery:
    """shipwright-plan resume from various checkpoints."""

    def test_resume_after_interview(self, trilogy_project):
        """Resume detects plan interview → skip to step 3."""
        planning = trilogy_project / ".shipwright" / "planning"
        self._setup_spec(planning)

        spec = planning / "01-auth" / "spec.md"

        run_script(PLAN_PLUGIN, "checks", "setup-planning-session.py", [
            "--file", str(spec), "--plugin-root", str(PLAN_PLUGIN),
        ])

        (spec.parent / "shipwright_plan_interview.md").write_text("# Interview\n")

        result = run_script(PLAN_PLUGIN, "checks", "setup-planning-session.py", [
            "--file", str(spec), "--plugin-root", str(PLAN_PLUGIN),
        ])
        assert result["mode"] == "resume"
        assert result["resume_from_step"] == 3

    def test_resume_after_plan(self, trilogy_project):
        """Resume detects plan.md + review marker with manifest → skip to step 6."""
        planning = trilogy_project / ".shipwright" / "planning"
        self._setup_spec(planning)

        spec = planning / "01-auth" / "spec.md"

        run_script(PLAN_PLUGIN, "checks", "setup-planning-session.py", [
            "--file", str(spec), "--plugin-root", str(PLAN_PLUGIN),
        ])

        (spec.parent / "shipwright_plan_interview.md").write_text("# Interview\n")
        (spec.parent / "plan.md").write_text(
            "<!-- SECTION_MANIFEST\n01-models\nEND_MANIFEST -->\n# Plan\n"
        )
        # v0.3.0+ gate: Step 5 must have written the review marker
        _write_review_marker(spec.parent)

        result = run_script(PLAN_PLUGIN, "checks", "setup-planning-session.py", [
            "--file", str(spec), "--plugin-root", str(PLAN_PLUGIN),
        ])
        assert result["resume_from_step"] == 6  # sections declared but not written

    def test_resume_after_partial_sections(self, trilogy_project):
        """Resume detects partial sections → step 6."""
        planning = trilogy_project / ".shipwright" / "planning"
        self._setup_spec(planning)

        spec = planning / "01-auth" / "spec.md"

        run_script(PLAN_PLUGIN, "checks", "setup-planning-session.py", [
            "--file", str(spec), "--plugin-root", str(PLAN_PLUGIN),
        ])

        (spec.parent / "shipwright_plan_interview.md").write_text("# Interview\n")
        (spec.parent / "plan.md").write_text(
            "<!-- SECTION_MANIFEST\n01-models\n02-routes\nEND_MANIFEST -->\n"
        )
        sections = spec.parent / "sections"
        sections.mkdir(exist_ok=True)
        (sections / "01-models.md").write_text("# Done\n")
        # 02-routes missing
        _write_review_marker(spec.parent)

        result = run_script(PLAN_PLUGIN, "checks", "setup-planning-session.py", [
            "--file", str(spec), "--plugin-root", str(PLAN_PLUGIN),
        ])
        assert result["resume_from_step"] == 6
        assert result["state"]["sections_missing"] == ["02-routes"]

    def test_resume_all_sections_done(self, trilogy_project):
        """All sections written → step 8 (E2E/completion)."""
        planning = trilogy_project / ".shipwright" / "planning"
        self._setup_spec(planning)

        spec = planning / "01-auth" / "spec.md"

        run_script(PLAN_PLUGIN, "checks", "setup-planning-session.py", [
            "--file", str(spec), "--plugin-root", str(PLAN_PLUGIN),
        ])

        (spec.parent / "shipwright_plan_interview.md").write_text("# Interview\n")
        (spec.parent / "plan.md").write_text(
            "<!-- SECTION_MANIFEST\n01-models\nEND_MANIFEST -->\n"
        )
        sections = spec.parent / "sections"
        sections.mkdir(exist_ok=True)
        (sections / "01-models.md").write_text("# Done\n")
        _write_review_marker(spec.parent)

        result = run_script(PLAN_PLUGIN, "checks", "setup-planning-session.py", [
            "--file", str(spec), "--plugin-root", str(PLAN_PLUGIN),
        ])
        assert result["resume_from_step"] == 8

    def _setup_spec(self, planning: Path):
        """Create a minimal spec for plan testing."""
        auth = planning / "01-auth"
        auth.mkdir(exist_ok=True)
        spec = auth / "spec.md"
        if not spec.exists():
            spec.write_text("# Auth Spec\n\nImplement authentication.\n")


class TestCrossPluginConfig:
    """Config files from one plugin are readable by the next."""

    def test_project_config_readable_by_build(self, trilogy_project):
        """shipwright_project_config.json is valid JSON for downstream."""
        planning = trilogy_project / ".shipwright" / "planning"

        # Create project config via project plugin
        (planning / "requirements.md").exists()  # already exists from fixture
        run_script(PROJECT_PLUGIN, "checks", "setup-session.py", [
            "--file", str(planning / "requirements.md"),
            "--plugin-root", str(PROJECT_PLUGIN),
        ])
        (planning / "shipwright_project_interview.md").write_text("# Interview\n")
        (planning / "project-manifest.md").write_text(
            "<!-- SPLIT_MANIFEST\n01-auth\nEND_MANIFEST -->\n"
        )
        run_script(PROJECT_PLUGIN, "checks", "create-split-dirs.py", [
            "--planning-dir", str(planning),
        ])
        (planning / "01-auth" / "spec.md").write_text("# Auth\n")

        run_script(PROJECT_PLUGIN, "checks", "write-project-config.py", [
            "--planning-dir", str(planning),
            "--profile", "supabase-nextjs",
            "--scope", "full_app",
            "--project-root", str(trilogy_project),
        ])

        # Read config and verify it's valid for downstream
        config_path = trilogy_project / "shipwright_project_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        assert config["profile"] == "supabase-nextjs"
        assert config["scope"] == "full_app"
        assert isinstance(config["splits"], list)
        assert config["splits"][0]["name"] == "01-auth"
        assert config["splits"][0]["status"] == "not_started"

        # Layer-3 drift safety net.
        _assert_no_legacy_artifact_dirs(trilogy_project)

    def test_build_config_tracks_progress(self, trilogy_project):
        """Build config tracks section completion across multiple calls."""
        (trilogy_project / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)

        # Complete first section
        run_script(BUILD_PLUGIN, "tools", "update_section_state.py", [
            "--section", "01-models",
            "--status", "complete",
            "--commit", "aaa111",
            "--project-root", str(trilogy_project),
        ])

        # Complete second section
        run_script(BUILD_PLUGIN, "tools", "update_section_state.py", [
            "--section", "02-routes",
            "--status", "complete",
            "--commit", "bbb222",
            "--project-root", str(trilogy_project),
        ])

        # Verify both tracked
        config = json.loads(
            (trilogy_project / "shipwright_build_config.json").read_text(encoding="utf-8")
        )
        sections = {s["name"]: s for s in config["sections"]}

        assert sections["01-models"]["status"] == "complete"
        assert sections["01-models"]["commit"] == "aaa111"
        assert sections["02-routes"]["status"] == "complete"
        assert sections["02-routes"]["commit"] == "bbb222"

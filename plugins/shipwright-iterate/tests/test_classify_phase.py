"""Unit tests for classify_phase.py — regression coverage for the 'Build a ToDo-App' bug."""

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "lib"),
)

from classify_phase import classify


class TestPhaseClassification:
    def test_design_strong_signal(self):
        result = classify("design a landing page")
        assert result["phase"] == "design"

    def test_test_phase(self):
        result = classify("write tests for login")
        assert result["phase"] == "test"

    def test_deploy_phase(self):
        result = classify("deploy to production")
        assert result["phase"] == "deploy"

    def test_implement_is_build(self):
        result = classify("implement auth hook")
        assert result["phase"] == "build"

    def test_refactor_is_build(self):
        result = classify("refactor the adapter")
        assert result["phase"] == "build"

    def test_fix_bug_is_test(self):
        result = classify("fix bug in auth")
        assert result["phase"] == "test"

    def test_audit_is_compliance(self):
        result = classify("audit the SBOM")
        assert result["phase"] == "compliance"

    def test_empty_input_defaults_to_project(self):
        result = classify("")
        assert result["phase"] == "project"
        assert result["confidence"] == 0.0

    # --- Regression: the bug the user hit ---

    def test_build_a_todo_app_is_project_not_build(self):
        """Regression: 'Build a ToDo-App' used to classify as 'build' because the
        word 'build' was a BUILD-phase keyword and tiebreaker favored build over
        project. The word 'build' in a user title almost always means 'create',
        not the Shipwright build phase. Fix: drop 'build' from the build keyword
        set and reorder PHASE_PRIORITY so project wins ties."""
        result = classify("Build a ToDo-App")
        assert result["phase"] == "project", (
            f"'Build a ToDo-App' should classify as 'project' (create-a-new-app intent), "
            f"got {result['phase']}"
        )

    def test_build_a_landing_page_is_design(self):
        """'Build a landing page' should still classify as design because
        'landing' is in the design keyword set. The 'build' verb at the start
        should not override that signal."""
        result = classify("Build a landing page")
        assert result["phase"] == "design"

    def test_build_a_new_website_is_project(self):
        """Another create-new-app phrasing."""
        result = classify("Build a new website")
        assert result["phase"] == "project"

    def test_code_a_function_is_build(self):
        """'code' keyword still wins build."""
        result = classify("code a function to parse dates")
        assert result["phase"] == "build"

    def test_project_word_is_project(self):
        result = classify("set up the project scaffolding")
        assert result["phase"] == "project"

"""Tests for suggest_iterate.py phase router hook.

Tests the multilingual phase detection and routing logic.
Does NOT test the classify_intent fallback (that's tested separately in shipwright-iterate).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "suggest_iterate.py"

# Import the module directly for unit testing helper functions
sys.path.insert(0, str(HOOK_SCRIPT.parent))
from suggest_iterate import detect_phase_intent, matches_phase


# --- Unit tests for pattern matching ---


class TestMatchesPhase:
    """Test multilingual pattern matching for each phase."""

    @pytest.mark.parametrize("prompt", [
        "run tests",
        "run the tests",
        "execute test suite",
        "check unit tests",
        "verify e2e",
        "check design fidelity",
    ])
    def test_test_phase_english(self, prompt):
        assert matches_phase(prompt, "test")

    @pytest.mark.parametrize("prompt", [
        "tests laufen lassen",
        "tests ausführen",
        "tests machen",
        "teste das",
        "nochmal tests",
    ])
    def test_test_phase_german(self, prompt):
        assert matches_phase(prompt, "test")

    @pytest.mark.parametrize("prompt", [
        "deploy to production",
        "push to prod",
        "go live",
        "rollback the deployment",
    ])
    def test_deploy_phase_english(self, prompt):
        assert matches_phase(prompt, "deploy")

    @pytest.mark.parametrize("prompt", [
        "bitte deployen",
        "veröffentlichen",
        "ausrollen auf staging",
        "live stellen",
    ])
    def test_deploy_phase_german(self, prompt):
        assert matches_phase(prompt, "deploy")

    @pytest.mark.parametrize("prompt", [
        "generate compliance report",
        "create audit documentation",
        "show traceability matrix",
        "generate SBOM",
    ])
    def test_compliance_phase(self, prompt):
        assert matches_phase(prompt, "compliance")

    @pytest.mark.parametrize("prompt", [
        "create changelog",
        "generate release notes",
        "tag release",
        "version bump",
    ])
    def test_changelog_phase(self, prompt):
        assert matches_phase(prompt, "changelog")

    @pytest.mark.parametrize("prompt", [
        "replan the implementation",
        "create an implementation plan",
        "neu planen",
        "umplanen wegen neuer Anforderungen",
    ])
    def test_plan_phase(self, prompt):
        assert matches_phase(prompt, "plan")

    @pytest.mark.parametrize("prompt", [
        "design update the login screen",
        "mockup ändern",
        "wireframe erstellen",
        "layout überarbeiten",
    ])
    def test_design_phase(self, prompt):
        assert matches_phase(prompt, "design")


class TestDetectPhaseIntent:
    """Test that detect_phase_intent returns correct phase or None."""

    def test_returns_test_for_english(self):
        assert detect_phase_intent("please run tests") == "test"

    def test_returns_test_for_german(self):
        assert detect_phase_intent("tests nochmal laufen lassen") == "test"

    def test_returns_deploy(self):
        assert detect_phase_intent("deploy to staging") == "deploy"

    def test_returns_compliance(self):
        assert detect_phase_intent("generate compliance report") == "compliance"

    def test_returns_none_for_code_change(self):
        """Code changes should NOT match any phase — falls through to iterate."""
        assert detect_phase_intent("fix the login button color") is None

    def test_returns_none_for_greeting(self):
        assert detect_phase_intent("hello how are you") is None

    def test_returns_none_for_vague_request(self):
        assert detect_phase_intent("I need help with something") is None


class TestNonMatches:
    """Ensure prompts don't false-positive on wrong phases."""

    def test_fix_bug_not_test(self):
        """'fix a bug' should NOT trigger test phase."""
        assert not matches_phase("fix the authentication bug", "test")

    def test_plan_word_in_sentence(self):
        """'plan' alone shouldn't trigger — needs 'replan' or 'implementation plan'."""
        assert not matches_phase("I plan to fix this later", "plan")

    def test_deploy_in_unrelated(self):
        assert not matches_phase("the employee onboarding workflow is broken", "deploy")


# --- Integration tests via subprocess ---


class TestHookIntegration:
    """Test the full hook script via subprocess."""

    def _run_hook(self, prompt: str, cwd: str, config: dict | None = None) -> subprocess.CompletedProcess:
        """Run suggest_iterate.py as subprocess with given stdin."""
        if config is not None:
            config_path = Path(cwd) / "shipwright_run_config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

        stdin_data = json.dumps({"prompt": prompt, "cwd": cwd})
        return subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=stdin_data,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_no_config_exits_silently(self, tmp_path):
        result = self._run_hook("run tests please", str(tmp_path))
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_slash_command_skipped(self, tmp_path):
        result = self._run_hook("/shipwright-test", str(tmp_path), config={"status": "complete"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_short_message_skipped(self, tmp_path):
        result = self._run_hook("hi", str(tmp_path), config={"status": "complete"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_completed_pipeline_routes_to_test(self, tmp_path):
        result = self._run_hook("run the tests again", str(tmp_path), config={"status": "complete"})
        assert result.returncode == 0
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        assert "/shipwright-test" in context
        assert "test" in context.lower()

    def test_completed_pipeline_routes_to_deploy(self, tmp_path):
        result = self._run_hook("deploy to production now", str(tmp_path), config={"status": "complete"})
        assert result.returncode == 0
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        assert "/shipwright-deploy" in context

    def test_in_progress_warns_on_mismatch(self, tmp_path):
        result = self._run_hook(
            "run the tests",
            str(tmp_path),
            config={"status": "in_progress", "current_step": "build"},
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        assert "mismatch" in context.lower() or "build" in context

    def test_in_progress_no_output_when_matching(self, tmp_path):
        """If user intent matches current step, no additional context needed."""
        result = self._run_hook(
            "run the tests",
            str(tmp_path),
            config={"status": "in_progress", "current_step": "test"},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_in_progress_post_test_falls_through_to_iterate(self, tmp_path):
        """After test completion, non-phase prompts route to classify_for_iterate."""
        result = self._run_hook(
            "add a filter for completed tasks in the sidebar",
            str(tmp_path),
            config={
                "status": "in_progress",
                "current_step": "changelog",
                "completed_steps": ["project", "design", "plan", "build", "test"],
            },
        )
        assert result.returncode == 0
        if result.stdout.strip():
            output = json.loads(result.stdout)
            context = output["hookSpecificOutput"]["additionalContext"]
            assert "/shipwright-iterate" in context
        # If classify_for_iterate returns None (low confidence), empty stdout is
        # also acceptable — the key regression is that the hook no longer crashes
        # or silently drops post-test prompts due to the classify import bug.

    def test_in_progress_pre_test_does_not_fall_through(self, tmp_path):
        """Before test completion, non-phase prompts get no output (early phases)."""
        result = self._run_hook(
            "add a filter for completed tasks in the sidebar",
            str(tmp_path),
            config={
                "status": "in_progress",
                "current_step": "build",
                "completed_steps": ["project", "design", "plan"],
            },
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_in_progress_post_test_phase_keyword_still_warns(self, tmp_path):
        """Post-test deploy intent still triggers intent-mismatch warning."""
        result = self._run_hook(
            "deploy to production",
            str(tmp_path),
            config={
                "status": "in_progress",
                "current_step": "changelog",
                "completed_steps": ["project", "design", "plan", "build", "test"],
            },
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        assert "mismatch" in context.lower()
        assert "/shipwright-deploy" in context

    def test_classify_for_iterate_import_path_resolves(self):
        """Regression: classify_for_iterate must find classify_intent.py at repo root.

        Previously used .parent.parent.parent which resolves to shared/, not the
        repo root, silently breaking every iterate fallback via ImportError.
        """
        from suggest_iterate import classify_for_iterate  # noqa: F401
        repo_root = HOOK_SCRIPT.parent.parent.parent.parent
        assert (repo_root / "plugins" / "shipwright-iterate" / "scripts" / "lib" / "classify_intent.py").exists()

    def test_german_prompt_routes_correctly(self, tmp_path):
        result = self._run_hook("tests nochmal laufen lassen", str(tmp_path), config={"status": "complete"})
        assert result.returncode == 0
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        assert "/shipwright-test" in context

    # UserPromptSubmit's hookSpecificOutput MUST carry hookEventName or Claude
    # Code rejects the output (iterate-2026-05-29-fix-suggest-iterate-hookeventname).
    # The AST meta-test (test_hook_output_schema.py) covers all 3 emission paths
    # statically; these two deterministic paths assert the runtime output.
    @pytest.mark.parametrize("prompt,config", [
        ("run the tests again", {"status": "complete"}),
        ("deploy to production", {"status": "in_progress", "current_step": "build"}),
    ])
    def test_emitted_output_sets_hookeventname(self, tmp_path, prompt, config):
        result = self._run_hook(prompt, str(tmp_path), config=config)
        assert result.returncode == 0 and result.stdout.strip()
        hso = json.loads(result.stdout)["hookSpecificOutput"]
        assert hso.get("hookEventName") == "UserPromptSubmit", (
            f"must set hookEventName=UserPromptSubmit; got {hso.get('hookEventName')!r}"
        )

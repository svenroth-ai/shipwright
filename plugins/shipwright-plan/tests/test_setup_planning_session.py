"""Tests for setup-planning-session.py script."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "checks" / "setup-planning-session.py")


def run_setup(args: list[str], cwd: str | None = None, env_overrides: dict | None = None) -> dict:
    """Run setup script and parse JSON output.

    Args:
        cwd: Working dir for the subprocess. Tests that care about the
            external review status should pass an empty tmp_path so the
            script's load_shipwright_env() does not pick up the repo's
            real .env.local.
        env_overrides: Env vars to set/unset on top of os.environ. Keys
            mapped to None are removed.
    """
    env = os.environ.copy()
    if env_overrides:
        for k, v in env_overrides.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        env=env,
    )
    return json.loads(result.stdout)


def test_setup_new_session(sample_spec):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--file", str(sample_spec),
        "--plugin-root", plugin_root,
        "--session-id", "plan-test-123",
    ])
    assert output["success"] is True
    assert output["mode"] == "new"
    assert output["resume_from_step"] == 1


def test_setup_resume_session(sample_spec):
    plugin_root = str(Path(__file__).resolve().parent.parent)

    # First run
    run_setup(["--file", str(sample_spec), "--plugin-root", plugin_root])

    # Second run
    output = run_setup(["--file", str(sample_spec), "--plugin-root", plugin_root])
    assert output["success"] is True
    assert output["mode"] == "resume"


def test_setup_invalid_file(tmp_path):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup([
        "--file", str(tmp_path / "nonexistent.md"),
        "--plugin-root", plugin_root,
    ])
    assert output["success"] is False
    assert "not found" in output["error"]


def test_setup_creates_sections_dir(sample_spec):
    plugin_root = str(Path(__file__).resolve().parent.parent)
    run_setup(["--file", str(sample_spec), "--plugin-root", plugin_root])
    assert (sample_spec.parent / "sections").is_dir()


_CLEAN_REVIEW_ENV = {
    "OPENROUTER_API_KEY": None,
    "GEMINI_API_KEY": None,
    "GOOGLE_API_KEY": None,
    "OPENAI_API_KEY": None,
}


def test_setup_external_review_status_missing_keys(sample_spec, tmp_path):
    """No API keys and CWD without .env.local → status: missing_keys."""
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup(
        ["--file", str(sample_spec), "--plugin-root", plugin_root],
        cwd=str(tmp_path),
        env_overrides=_CLEAN_REVIEW_ENV,
    )
    assert output["success"] is True
    assert output["external_review_status"] == "missing_keys"
    assert output["external_review_enabled"] is False  # compat alias


def test_setup_external_review_status_available(sample_spec, tmp_path):
    """OPENROUTER_API_KEY set → status: available."""
    plugin_root = str(Path(__file__).resolve().parent.parent)
    output = run_setup(
        ["--file", str(sample_spec), "--plugin-root", plugin_root],
        cwd=str(tmp_path),
        env_overrides={**_CLEAN_REVIEW_ENV, "OPENROUTER_API_KEY": "sk-or-test-123"},
    )
    assert output["success"] is True
    assert output["external_review_status"] == "available"
    assert output["external_review_enabled"] is True


def _seed_resume(planning_dir: Path, *, with_marker: bool) -> None:
    """Prepare a planning dir that looks like a mid-flight session."""
    (planning_dir / "shipwright_plan_session.json").write_text(
        json.dumps({"spec_file_hash": "sha256:stub", "session_created_at": "2026-04-14T00:00:00Z"})
    )
    (planning_dir / "plan.md").write_text(
        "<!-- SECTION_MANIFEST\n01-auth\nEND_MANIFEST -->\n\n# Plan\n"
    )
    (planning_dir / "sections").mkdir(exist_ok=True)
    if with_marker:
        (planning_dir / "external_review_state.json").write_text(
            json.dumps({"status": "completed", "provider": "openrouter"})
        )


def test_setup_resume_forces_step5_when_marker_missing(sample_spec, tmp_path):
    """plan.md exists but external_review_state.json missing → resume_step = 5."""
    plugin_root = str(Path(__file__).resolve().parent.parent)
    _seed_resume(sample_spec.parent, with_marker=False)

    output = run_setup(
        ["--file", str(sample_spec), "--plugin-root", plugin_root],
        cwd=str(tmp_path),
        env_overrides=_CLEAN_REVIEW_ENV,
    )
    assert output["success"] is True
    assert output["mode"] == "resume"
    assert output["resume_from_step"] == 5
    assert output["state"]["review_state_exists"] is False


def test_setup_resume_advances_when_marker_present(sample_spec, tmp_path):
    """plan.md + external_review_state.json + sections missing → resume_step = 6."""
    plugin_root = str(Path(__file__).resolve().parent.parent)
    _seed_resume(sample_spec.parent, with_marker=True)

    output = run_setup(
        ["--file", str(sample_spec), "--plugin-root", plugin_root],
        cwd=str(tmp_path),
        env_overrides=_CLEAN_REVIEW_ENV,
    )
    assert output["success"] is True
    assert output["mode"] == "resume"
    assert output["resume_from_step"] == 6
    assert output["state"]["review_state_exists"] is True

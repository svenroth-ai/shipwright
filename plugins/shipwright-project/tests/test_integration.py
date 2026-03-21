"""Integration tests for shipwright-project."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

CHECKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "checks"


def run_script(script_name: str, args: list[str]) -> dict:
    """Run a check script and parse JSON output."""
    script = str(CHECKS_DIR / script_name)
    result = subprocess.run(
        [sys.executable, script] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


@pytest.mark.integration
def test_full_flow(tmp_path):
    """Test setup → create dirs flow."""
    # 1. Create requirements
    planning = tmp_path / "planning"
    planning.mkdir()
    req = planning / "requirements.md"
    req.write_text("# Test\n\nBuild something.\n")

    plugin_root = str(Path(__file__).resolve().parent.parent)

    # 2. Run setup
    setup_result = run_script("setup-session.py", [
        "--file", str(req),
        "--plugin-root", plugin_root,
        "--session-id", "integration-test",
    ])
    assert setup_result["success"] is True
    assert setup_result["mode"] == "new"

    # 3. Simulate interview + manifest (normally done by SKILL.md)
    interview = planning / "shipwright_project_interview.md"
    interview.write_text("# Interview\n\nSingle split project.\n")

    manifest = planning / "project-manifest.md"
    manifest.write_text("<!-- SPLIT_MANIFEST\n01-core\nEND_MANIFEST -->\n\n# Manifest\n\nOne split.\n")

    # 4. Create dirs
    dirs_result = run_script("create-split-dirs.py", [
        "--planning-dir", str(planning),
    ])
    assert dirs_result["success"] is True
    assert dirs_result["created"] == ["01-core"]

    # 5. Verify resume detects progress
    resume_result = run_script("setup-session.py", [
        "--file", str(req),
        "--plugin-root", plugin_root,
        "--session-id", "integration-test",
    ])
    assert resume_result["mode"] == "resume"
    assert resume_result["resume_from_step"] == 6  # Spec generation

    # 6. Write spec
    (planning / "01-core" / "spec.md").write_text("# Core Spec\n")

    # 7. Verify complete state
    final_result = run_script("setup-session.py", [
        "--file", str(req),
        "--plugin-root", plugin_root,
        "--session-id", "integration-test",
    ])
    assert final_result["resume_from_step"] == 7  # Scaffolding

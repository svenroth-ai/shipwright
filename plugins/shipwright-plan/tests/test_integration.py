"""Integration tests for shipwright-plan."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

CHECKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "checks"


def run_script(script_name: str, args: list[str]) -> dict:
    script = str(CHECKS_DIR / script_name)
    result = subprocess.run(
        [sys.executable, script] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


@pytest.mark.integration
def test_full_planning_flow(tmp_path):
    """Test setup → check sections flow."""
    planning = tmp_path / "planning"
    planning.mkdir()
    (planning / "sections").mkdir()

    spec = planning / "spec.md"
    spec.write_text("# Test Spec\n\nBuild auth module.\n")

    plugin_root = str(Path(__file__).resolve().parent.parent)

    # 1. Setup
    setup_result = run_script("setup-planning-session.py", [
        "--file", str(spec),
        "--plugin-root", plugin_root,
        "--session-id", "integration-plan-test",
    ])
    assert setup_result["success"] is True
    assert setup_result["mode"] == "new"

    # 2. Simulate interview
    (planning / "shipwright_plan_interview.md").write_text("# Interview\n\nDone.\n")

    # 3. Simulate plan with manifest
    plan = planning / "plan.md"
    plan.write_text(
        "<!-- SECTION_MANIFEST\n01-models\n02-routes\nEND_MANIFEST -->\n\n"
        "# Plan\n\nTwo sections.\n"
    )

    # 4. Check sections — should be missing
    check_result = run_script("check-sections.py", [
        "--planning-dir", str(planning),
    ])
    assert check_result["success"] is False
    assert check_result["missing"] == ["01-models", "02-routes"]

    # 5. Write sections
    (planning / "sections" / "01-models.md").write_text("# Section: 01-models\n")
    (planning / "sections" / "02-routes.md").write_text("# Section: 02-routes\n")

    # 6. Check again — should pass
    check_result = run_script("check-sections.py", [
        "--planning-dir", str(planning),
    ])
    assert check_result["success"] is True
    assert check_result["missing"] == []

    # 7. Resume should detect step 8 (E2E/completion)
    resume_result = run_script("setup-planning-session.py", [
        "--file", str(spec),
        "--plugin-root", plugin_root,
        "--session-id", "integration-plan-test",
    ])
    assert resume_result["mode"] == "resume"
    assert resume_result["resume_from_step"] == 8

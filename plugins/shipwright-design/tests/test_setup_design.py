"""Tests for setup-design-session.py."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "checks" / "setup-design-session.py")


def run_setup(args: list[str]) -> dict:
    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_setup_new_project(tmp_project, plugin_root):
    output = run_setup([
        "--project-root", str(tmp_project),
        "--plugin-root", str(plugin_root),
    ])

    assert output["success"] is True
    assert output["mode"] == "new"
    assert output["profile"] == "supabase-nextjs"
    assert len(output["specs_found"]) >= 1
    assert "01-auth" in output["specs_found"][0]


def test_setup_creates_dirs(tmp_project, plugin_root):
    run_setup([
        "--project-root", str(tmp_project),
        "--plugin-root", str(plugin_root),
    ])

    assert (tmp_project / "designs" / "screens").is_dir()
    assert (tmp_project / "designs" / "flows").is_dir()
    assert (tmp_project / "designs" / "uploads").is_dir()


def test_setup_iterate_mode(tmp_project_with_designs, plugin_root):
    output = run_setup([
        "--project-root", str(tmp_project_with_designs),
        "--plugin-root", str(plugin_root),
    ])

    assert output["mode"] == "iterate"
    assert len(output["existing_designs"]["screens"]) == 2


def test_setup_upload_mode(tmp_project, plugin_root):
    uploads = tmp_project / "designs" / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "mockup.png").write_text("fake")

    output = run_setup([
        "--project-root", str(tmp_project),
        "--plugin-root", str(plugin_root),
    ])

    assert output["mode"] == "upload"
    assert len(output["existing_designs"]["uploads"]) == 1


def test_setup_no_project_config(tmp_path, plugin_root):
    """Works even without shipwright_project_config.json."""
    project = tmp_path / "bare-project"
    project.mkdir()

    output = run_setup([
        "--project-root", str(project),
        "--plugin-root", str(plugin_root),
    ])

    assert output["success"] is True
    assert output["profile"] == "supabase-nextjs"  # default

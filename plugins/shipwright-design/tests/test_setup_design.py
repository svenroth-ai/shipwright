"""Tests for setup-design-session.py."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "checks" / "setup-design-session.py")
_REPO_ROOT = Path(__file__).resolve().parents[3]
_GATE_POLICY_CLI = _REPO_ROOT / "shared" / "scripts" / "tools" / "resolve_gate_policy.py"


def _resolve_gate(gate_id: str, tmp_path: Path) -> dict:
    """Run the real gate-policy resolver, forced to the fully-automated
    single-session mode — the strictest test of whether a gate can be
    skipped without a human. ``--project-root`` is an empty tmp dir so no
    real run_config is picked up."""
    proc = subprocess.run(
        [sys.executable, str(_GATE_POLICY_CLI), "--gate", gate_id,
         "--mode", "single_session", "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(proc.stdout)


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

    assert (tmp_project / ".shipwright" / "designs" / "screens").is_dir()
    assert (tmp_project / ".shipwright" / "designs" / "flows").is_dir()
    assert (tmp_project / ".shipwright" / "designs" / "uploads").is_dir()
    # Canonical only - intentional negative-assertion against legacy.  # artifact-path-canon: legacy
    assert not (tmp_project / "designs").exists()  # artifact-path-canon: legacy


def test_setup_iterate_mode(tmp_project_with_designs, plugin_root):
    output = run_setup([
        "--project-root", str(tmp_project_with_designs),
        "--plugin-root", str(plugin_root),
    ])

    assert output["mode"] == "iterate"
    assert len(output["existing_designs"]["screens"]) == 2


def test_setup_upload_mode(tmp_project, plugin_root):
    uploads = tmp_project / ".shipwright" / "designs" / "uploads"
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


# --- approval gates never auto-resolve, even under full automation ---------


@pytest.mark.covers("FR-01.04/AC07")
def test_preview_approval_gate_always_stops_for_a_human(tmp_path):
    """FR-01.04/AC07: the look and feel is put to a person for approval on
    the first representative screens, before the rest are generated — even
    the fully-automated single-session mode must stop here rather than
    auto-approve the visual direction."""
    result = _resolve_gate("design.preview-approval", tmp_path)
    assert result["should_stop"] is True
    assert result["effective_policy"] != "auto-default"


@pytest.mark.covers("FR-01.04/AC08")
def test_review_loop_finalize_gate_always_stops_for_a_human(tmp_path):
    """FR-01.04/AC08: design never declares itself finished on its own —
    the phase-exit sign-off gate stops for a human even under full
    automation, never resolving to an unattended auto-default."""
    result = _resolve_gate("design.review-loop-finalize", tmp_path)
    assert result["should_stop"] is True
    assert result["effective_policy"] != "auto-default"

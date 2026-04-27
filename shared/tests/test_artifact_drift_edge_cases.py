"""Edge-case tests for artifact drift detection (External-Review GPT-9 + GPT-10).

Surfaces runtime behavior the unit-test layers do not cover by themselves:

- **GPT-9 both-dirs-exist matrix:** what happens when a project has BOTH
  legacy ``<artifact>/`` and canonical ``.shipwright/<artifact>/``? The
  drift detector should still report the legacy presence (warn during
  in_progress, block during migrated). Reads must come from canonical.
- **GPT-10 generated-output content scan:** mockup HTML / manifest output
  emitted by setup-design-session.py must not embed legacy ``designs/``
  path strings. Caller passes canonical, so generators stay neutral.

Both tests use the ``designs`` migration entry (in_progress at
Sub-Iterate E land time). Tests pick up future artifacts automatically
via ``ARTIFACT_MIGRATIONS``.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO / "shared" / "scripts"


def _load_artifact_migrations():
    """Load ``lib.artifact_migrations`` without poisoning ``sys.modules['lib']``.

    Same pattern as integration-tests/test_core_trilogy_flow.py's Layer-3
    helper — the compliance plugin has its own ``lib/`` package that
    fights the shared one if loaded via plain import.
    """
    spec = importlib.util.spec_from_file_location(
        "_artifact_migrations_drift_edge",
        _SHARED_SCRIPTS / "lib" / "artifact_migrations.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_drift_hook(project_root: Path) -> subprocess.CompletedProcess:
    """Invoke check_artifact_drift.py on a project root, return result."""
    return subprocess.run(
        [
            sys.executable,
            str(_SHARED_SCRIPTS / "hooks" / "check_artifact_drift.py"),
        ],
        cwd=str(project_root),
        env={"SHIPWRIGHT_PROJECT_ROOT": str(project_root), "PATH": ""},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# GPT-9: both-dirs-exist runtime matrix
# ---------------------------------------------------------------------------


@pytest.fixture
def designs_migration():
    """The designs migration entry — skip if not active."""
    mod = _load_artifact_migrations()
    for mig in mod.ARTIFACT_MIGRATIONS:
        if mig["name"] == "designs":
            if mig["status"] == "pending":
                pytest.skip("designs migration is pending; nothing to test yet")
            return mig
    pytest.skip("designs migration entry not present in manifest")


def _seed_minimal_shipwright_project(project_root: Path) -> None:
    """Make a directory recognizable as a Shipwright project so
    ``resolve_project_root()`` accepts it.
    """
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps({"current_step": "design", "status": "in_progress"}),
        encoding="utf-8",
    )


def test_drift_detector_reports_both_dirs_present(tmp_path, designs_migration):
    """When a project has BOTH legacy `designs/` and canonical
    `.shipwright/designs/`, the drift detector must still surface the
    legacy directory.

    Severity depends on migration status:
    - in_progress → exit 0 with warn-style stderr + stale-folders.md
    - migrated    → exit 1 with structured JSON + stale-folders.md
    """
    project = tmp_path / "both-present"
    project.mkdir()
    _seed_minimal_shipwright_project(project)

    # Both directories exist; legacy has content (drift trigger).
    legacy = project / designs_migration["legacy_dirname"]
    legacy.mkdir()
    (legacy / "leftover.html").write_text("<html>old</html>", encoding="utf-8")

    canonical = project / designs_migration["canonical"]
    canonical.mkdir(parents=True)
    (canonical / "current.html").write_text("<html>new</html>", encoding="utf-8")

    result = _run_drift_hook(project)

    # Stale-folders report file must be present.
    report = project / ".shipwright" / "stale-folders.md"
    assert report.exists(), (
        f"Drift detector did not emit stale-folders.md\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    body = report.read_text(encoding="utf-8")
    # The artifact name and ".shipwright" must appear; the full canonical
    # path is rendered with native separators (backslashes on Windows),
    # so we check name + status + ".shipwright" presence rather than
    # the canonical literal.
    assert "designs" in body
    assert ".shipwright" in body
    assert designs_migration["status"] in body

    # Severity expectations.
    if designs_migration["status"] == "in_progress":
        assert result.returncode == 0, (
            f"in_progress drift should be warn-only, got rc={result.returncode}"
        )
    else:
        assert result.returncode == 1, (
            f"migrated drift should hard-gate, got rc={result.returncode}"
        )


def test_drift_detector_silent_on_canonical_only(tmp_path, designs_migration):
    """Canonical-only project must NOT trigger drift (nothing to report)."""
    project = tmp_path / "canonical-only"
    project.mkdir()
    _seed_minimal_shipwright_project(project)

    canonical = project / designs_migration["canonical"]
    canonical.mkdir(parents=True)
    (canonical / "current.html").write_text("<html>new</html>", encoding="utf-8")

    result = _run_drift_hook(project)

    # Self-heal: stale-folders.md must NOT exist for clean projects.
    report = project / ".shipwright" / "stale-folders.md"
    assert not report.exists(), (
        f"Drift detector wrote stale-folders.md for clean project: "
        f"{report.read_text(encoding='utf-8') if report.exists() else ''}"
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# GPT-10: generated-output content scan
# ---------------------------------------------------------------------------


def test_setup_design_session_output_has_no_legacy_path_strings(tmp_path):
    """Run setup-design-session.py end-to-end and verify the JSON output
    does not embed the legacy ``designs/`` path string. Catches the case
    where a path-construction site silently falls back to the legacy
    literal (unit tests pass with mocks; this exercises the real CLI).
    """
    project = tmp_path / "design-output-scan"
    project.mkdir()

    plugin_root = _REPO / "plugins" / "shipwright-design"
    script = plugin_root / "scripts" / "checks" / "setup-design-session.py"

    result = subprocess.run(
        [
            sys.executable, str(script),
            "--project-root", str(project),
            "--plugin-root", str(plugin_root),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, (
        f"setup-design-session.py failed: {result.stderr}"
    )

    # JSON stdout must not contain the legacy path as a substring.
    # Caveat: ``"existing_designs"`` is a dict-key (intentional, not a
    # path) — search for the path-shape ``"designs/`` with trailing slash.
    forbidden = '"designs/'
    assert forbidden not in result.stdout, (
        f"setup-design-session.py emitted legacy path string in JSON: "
        f"{result.stdout}"
    )

    # And the canonical structure exists on disk.
    assert (project / ".shipwright" / "designs").is_dir()
    assert not (project / "designs").exists()  # artifact-path-canon: legacy

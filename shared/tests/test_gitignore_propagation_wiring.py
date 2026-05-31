"""Wiring tests: adopt + project actually propagate the canonical block.

The merge logic itself is proven empirically in ``test_gitignore_canon_merge.py``.
These tests lock in that the two consumer surfaces are wired up:

* **project** (in-code): ``write-project-config.py --status complete`` runs
  the merge as a side-effect. Proven by a real subprocess run + a
  ``git check-ignore`` round-trip.
* **adopt** (SKILL-orchestrated CLI, kept out of the grandfathered
  ``generate_adoption_artifacts.py`` to respect the bloat baseline): the
  SKILL + step-e reference MUST document the ``gitignore_canon.py`` E.6
  invocation. A presence guard catches silent removal — the exact "applied
  by nobody" failure mode this iterate fixes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WRITE_PROJECT_CONFIG = (
    _REPO_ROOT
    / "plugins"
    / "shipwright-project"
    / "scripts"
    / "checks"
    / "write-project-config.py"
)
_ADOPT_SKILL = (
    _REPO_ROOT / "plugins" / "shipwright-adopt" / "skills" / "adopt" / "SKILL.md"
)
_ADOPT_STEP_E = (
    _REPO_ROOT
    / "plugins"
    / "shipwright-adopt"
    / "skills"
    / "adopt"
    / "references"
    / "step-e-artifact-generation.md"
)
_PROJECT_STEP_7 = (
    _REPO_ROOT
    / "plugins"
    / "shipwright-project"
    / "skills"
    / "project"
    / "references"
    / "step-7-scaffolding.md"
)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _require_git() -> None:
    if shutil.which("git") is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("git binary not found in CI — required for check-ignore probes")
        pytest.skip("git binary not available")


def test_project_write_config_merges_canonical_block(tmp_path: Path) -> None:
    """`write-project-config.py --status complete` propagates the block."""
    _require_git()
    _git("init", cwd=tmp_path)
    (tmp_path / "planning").mkdir()  # artifact-path-canon: legacy

    proc = subprocess.run(
        [
            sys.executable,
            str(_WRITE_PROJECT_CONFIG),
            "--planning-dir",
            str(tmp_path / "planning"),  # artifact-path-canon: legacy
            "--profile",
            "generic",
            "--scope",
            "full_app",
            "--status",
            "complete",
            "--project-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, f"script failed: {proc.stderr[-800:]}"

    gi = tmp_path / ".gitignore"
    assert gi.exists(), ".gitignore was not created by project scaffolding"
    text = gi.read_text(encoding="utf-8")
    assert "/.shipwright/agent_docs/runtime/" in text

    # Empirical: runtime ignored, canonical doc home tracked.
    (tmp_path / ".shipwright" / "agent_docs" / "runtime").mkdir(parents=True)
    (tmp_path / ".shipwright" / "agent_docs" / "runtime" / "h.md").write_text("x")
    (tmp_path / ".shipwright" / "agent_docs" / "architecture.md").write_text("x")
    assert _git(
        "check-ignore", ".shipwright/agent_docs/runtime/h.md", cwd=tmp_path
    ).returncode == 0
    assert _git(
        "check-ignore", ".shipwright/agent_docs/architecture.md", cwd=tmp_path
    ).returncode == 1


def test_adopt_skill_invokes_gitignore_canon_cli() -> None:
    skill = _ADOPT_SKILL.read_text(encoding="utf-8")
    step_e = _ADOPT_STEP_E.read_text(encoding="utf-8")
    assert "gitignore_canon.py" in skill, (
        "adopt SKILL.md must invoke the canonical gitignore merge CLI "
        "(Step E.6) — without it, framework ignore rules never reach "
        "adopted projects (the gap this iterate closes)."
    )
    assert "gitignore_canon" in step_e, (
        "step-e reference must document the canonical gitignore propagation"
    )


def test_project_step7_documents_canonical_merge() -> None:
    step7 = _PROJECT_STEP_7.read_text(encoding="utf-8")
    assert "gitignore_canon" in step7, (
        "project step-7 reference must document the canonical .gitignore merge"
    )

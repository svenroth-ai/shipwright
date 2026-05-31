"""Tests for `shared/scripts/tools/migrate_artifact_dir.py`.

The CLI moves a legacy top-level artifact directory (e.g. `planning/`) to its
canonical `.shipwright/<name>/` home for an existing user project. It must:

- be safe by default — refuse when the canonical destination already exists
  with content, refuse when the legacy dir doesn't exist, refuse on unknown
  artifact names
- support `--dry-run` that prints what *would* happen and changes nothing
- prefer `git mv` when the legacy dir is git-tracked, fall back to
  `shutil.move` for untracked workspaces
- surface a remediation hint on failure
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "shared" / "scripts" / "tools" / "migrate_artifact_dir.py"


def _import_tool():
    """Load the CLI module by file-spec to avoid sys.modules collisions."""
    spec = importlib.util.spec_from_file_location(
        "migrate_artifact_dir_under_test", TOOL_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tool():
    return _import_tool()


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Invoke the CLI as a subprocess so argparse + exit codes are exercised."""
    return subprocess.run(
        [sys.executable, str(TOOL_PATH), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _git_init(project: Path) -> None:
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=str(project), capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(project),
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(project),
        capture_output=True,
        check=True,
    )


class TestMigrateArtifactDirHappyPath:
    def test_moves_legacy_dir_to_canonical_location(self, tmp_path):
        legacy = tmp_path / "planning"
        legacy.mkdir()
        (legacy / "spec.md").write_text("# spec\n", encoding="utf-8")

        result = _run_cli(
            ["--artifact", "planning", "--project-root", str(tmp_path)], cwd=tmp_path
        )

        assert result.returncode == 0, result.stdout + result.stderr
        canonical = tmp_path / ".shipwright" / "planning"
        assert canonical.is_dir()
        assert (canonical / "spec.md").read_text(encoding="utf-8") == "# spec\n"
        assert not legacy.exists()

    def test_uses_git_mv_when_repo_tracks_legacy_dir(self, tmp_path):
        _git_init(tmp_path)
        legacy = tmp_path / "planning"
        legacy.mkdir()
        (legacy / "spec.md").write_text("# spec\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=str(tmp_path),
            capture_output=True,
            check=True,
        )

        result = _run_cli(
            ["--artifact", "planning", "--project-root", str(tmp_path)], cwd=tmp_path
        )

        assert result.returncode == 0, result.stdout + result.stderr
        canonical = tmp_path / ".shipwright" / "planning"
        assert canonical.is_dir()
        # Verify git knows about the move by checking porcelain output for renames
        porcelain = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert "R" in porcelain.stdout or "renamed" in porcelain.stdout.lower(), (
            f"expected rename markers in porcelain output, got: {porcelain.stdout!r}"
        )


class TestMigrateArtifactDirDryRun:
    def test_dry_run_does_not_move_anything(self, tmp_path):
        legacy = tmp_path / "planning"
        legacy.mkdir()
        (legacy / "spec.md").write_text("# spec\n", encoding="utf-8")

        result = _run_cli(
            ["--artifact", "planning", "--project-root", str(tmp_path), "--dry-run"],
            cwd=tmp_path,
        )

        assert result.returncode == 0
        assert legacy.exists()
        assert not (tmp_path / ".shipwright" / "planning").exists()
        assert "dry run" in result.stdout.lower()


class TestMigrateArtifactDirPreflight:
    def test_refuses_unknown_artifact(self, tmp_path):
        result = _run_cli(
            ["--artifact", "no-such-artifact", "--project-root", str(tmp_path)],
            cwd=tmp_path,
        )
        assert result.returncode != 0
        assert "unknown artifact" in (result.stdout + result.stderr).lower()

    def test_refuses_when_legacy_dir_missing(self, tmp_path):
        result = _run_cli(
            ["--artifact", "planning", "--project-root", str(tmp_path)], cwd=tmp_path
        )
        assert result.returncode != 0
        assert "legacy" in (result.stdout + result.stderr).lower()

    def test_refuses_when_canonical_target_already_has_content(self, tmp_path):
        legacy = tmp_path / "planning"
        legacy.mkdir()
        (legacy / "spec.md").write_text("# legacy spec\n", encoding="utf-8")

        canonical = tmp_path / ".shipwright" / "planning"
        canonical.mkdir(parents=True)
        (canonical / "other.md").write_text("# pre-existing\n", encoding="utf-8")

        result = _run_cli(
            ["--artifact", "planning", "--project-root", str(tmp_path)], cwd=tmp_path
        )

        assert result.returncode != 0
        out = result.stdout + result.stderr
        assert "canonical" in out.lower() and "already" in out.lower()
        # Nothing was moved
        assert legacy.exists()
        assert (canonical / "other.md").exists()

    def test_allows_when_canonical_target_is_empty_dir(self, tmp_path):
        """If `.shipwright/planning/` exists empty, that's fine — clean it up
        and proceed."""
        legacy = tmp_path / "planning"
        legacy.mkdir()
        (legacy / "spec.md").write_text("# spec\n", encoding="utf-8")
        (tmp_path / ".shipwright" / "planning").mkdir(parents=True)

        result = _run_cli(
            ["--artifact", "planning", "--project-root", str(tmp_path)], cwd=tmp_path
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert (tmp_path / ".shipwright" / "planning" / "spec.md").exists()


class TestMigrateArtifactDirOutput:
    def test_emits_remediation_hint_on_failure(self, tmp_path):
        result = _run_cli(
            ["--artifact", "no-such", "--project-root", str(tmp_path)], cwd=tmp_path
        )
        assert "remediation" in (result.stdout + result.stderr).lower() or \
               "available artifacts" in (result.stdout + result.stderr).lower()

    def test_emits_json_on_success_when_requested(self, tmp_path):
        legacy = tmp_path / "planning"
        legacy.mkdir()
        (legacy / "spec.md").write_text("# spec\n", encoding="utf-8")

        result = _run_cli(
            [
                "--artifact",
                "planning",
                "--project-root",
                str(tmp_path),
                "--json",
            ],
            cwd=tmp_path,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["success"] is True
        assert payload["artifact"] == "planning"
        assert payload["from"].endswith("planning")
        assert payload["to"].endswith("planning")
